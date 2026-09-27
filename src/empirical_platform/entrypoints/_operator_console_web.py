"""MILESTONE-086 -- the smallest web layer that can carry the Operator Console safely.

WHY THE STANDARD LIBRARY. The console is a local, single-operator product bound to
127.0.0.1. A web framework would add several third-party packages (and their audit
surface) to carry seven routes and five forms. Everything needed -- routing, form
parsing, cookies, a CSRF token, security headers, a threaded local server -- is in the
standard library (`wsgiref`, `http.cookies`, `urllib.parse`, `hmac`, `secrets`), so this
module implements exactly that and nothing more. There is no business logic here: the
application services in `usecases.operator_console` decide everything; this module
turns HTTP into calls and results into HTML.

SECURITY MODEL, STATED. (1) Bind to the loopback address only, by default and by the
launcher's refusal of anything else without an explicit flag. (2) Every state-changing
action is a POST carrying a CSRF token; the token is an HMAC over a per-process secret
and the browser's session cookie (HttpOnly, SameSite=Strict), so a page from another
origin cannot forge it and a stale tab from a previous process cannot replay it. (3)
Every POST answers with a 303 redirect, so a browser refresh never re-submits. (4) A
strict Content-Security-Policy allows only same-origin, inline-free assets, and the
page carries no script at all. (5) No credential exists in this process: the only
broker is the simulation. (6) The `environment` of an action is never read from the
request -- see `usecases.operator_console.ExecutionCapability`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from html import escape
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

__all__ = [
    "Request",
    "Response",
    "Router",
    "SecuritySession",
    "ThreadingWSGIServer",
    "html_response",
    "redirect",
    "serve",
]

_SESSION_COOKIE = "operator_console_session"
_MAXIMUM_BODY_BYTES = 64 * 1024

_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'self'; img-src 'self' data:; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
)


@dataclass(frozen=True, slots=True)
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    form: dict[str, list[str]]
    cookies: dict[str, str]
    headers: dict[str, str]

    def first(self, name: str, default: str = "") -> str:
        values = self.form.get(name) or self.query.get(name) or []
        return values[0] if values else default

    def all_form_keys(self) -> frozenset[str]:
        return frozenset(self.form)


@dataclass(slots=True)
class Response:
    status: str = "200 OK"
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""


def html_response(document: str, status: str = "200 OK") -> Response:
    body = document.encode("utf-8")
    return Response(
        status=status,
        headers=[
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
        body=body,
    )


def redirect(location: str) -> Response:
    """303 See Other: the answer to every POST, so a refresh never re-submits."""
    return Response(
        status="303 See Other", headers=[("Location", location), ("Content-Length", "0")]
    )


class SecuritySession:
    """Per-process secret, per-browser session cookie, HMAC CSRF token.

    The secret lives only in this process's memory; restarting the console invalidates
    every token a tab still holds, which is the intended behaviour -- an action prepared
    before a restart must be looked at again, never replayed.
    """

    def __init__(self) -> None:
        self._secret = secrets.token_bytes(32)

    def new_session_id(self) -> str:
        return secrets.token_urlsafe(24)

    def csrf_token(self, session_id: str) -> str:
        digest = hmac.new(self._secret, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest[:48]

    def token_is_valid(self, session_id: str | None, token: str | None) -> bool:
        if not session_id or not token:
            return False
        return hmac.compare_digest(self.csrf_token(session_id), token)


Handler = Callable[[Request, str], Response]


class Router:
    """Exact-path routing. No pattern language; the console has few pages."""

    def __init__(self, security: SecuritySession) -> None:
        self._routes: dict[tuple[str, str], Handler] = {}
        self._security = security
        self._not_found: Callable[[Request], Response] | None = None
        self._refused: Callable[[Request, str], Response] | None = None

    def get(self, path: str, handler: Handler) -> None:
        self._routes[("GET", path)] = handler

    def post(self, path: str, handler: Handler) -> None:
        self._routes[("POST", path)] = handler

    def on_not_found(self, handler: Callable[[Request], Response]) -> None:
        self._not_found = handler

    def on_refused(self, handler: Callable[[Request, str], Response]) -> None:
        self._refused = handler

    # -- WSGI ----------------------------------------------------------------------

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]:
        request = _read_request(environ)
        session_id = request.cookies.get(_SESSION_COOKIE)
        new_cookie = None
        if not session_id:
            session_id = self._security.new_session_id()
            new_cookie = session_id
        csrf = self._security.csrf_token(session_id)

        handler = self._routes.get((request.method, request.path))
        if handler is None:
            if request.method not in {"GET", "POST"}:
                response = Response(
                    status="405 Method Not Allowed", headers=[("Allow", "GET, POST")]
                )
            elif self._not_found is not None:
                response = self._not_found(request)
            else:
                response = html_response("<h1>Not found</h1>", "404 Not Found")
        elif request.method == "POST" and not self._security.token_is_valid(
            request.cookies.get(_SESSION_COOKIE), request.first("csrf_token")
        ):
            # A POST without the browser's own token: a cross-site form, a stale tab from a
            # previous process, or a hand-made request. Nothing is executed.
            reason = (
                "This action was not accepted because the page it came from is out of date "
                "or did not come from this console. Nothing was done. Open the page again."
            )
            response = (
                self._refused(request, reason)
                if self._refused is not None
                else html_response(f"<h1>Refused</h1><p>{escape(reason)}</p>", "403 Forbidden")
            )
        else:
            response = handler(request, csrf)

        headers = list(response.headers)
        headers.extend(_SECURITY_HEADERS)
        if new_cookie is not None:
            cookie: SimpleCookie = SimpleCookie()
            cookie[_SESSION_COOKIE] = new_cookie
            cookie[_SESSION_COOKIE]["httponly"] = True
            cookie[_SESSION_COOKIE]["samesite"] = "Strict"
            cookie[_SESSION_COOKIE]["path"] = "/"
            headers.append(("Set-Cookie", cookie.output(header="").strip()))
        start_response(response.status, headers)
        return [response.body]


def _read_request(environ: dict[str, Any]) -> Request:
    method = str(environ.get("REQUEST_METHOD", "GET")).upper()
    path = str(environ.get("PATH_INFO", "/")) or "/"
    query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
    form: dict[str, list[str]] = {}
    if method == "POST":
        content_type = str(environ.get("CONTENT_TYPE", ""))
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if 0 < length <= _MAXIMUM_BODY_BYTES and content_type.startswith(
            "application/x-www-form-urlencoded"
        ):
            body = environ["wsgi.input"].read(length)
            form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    cookies: dict[str, str] = {}
    raw_cookie = environ.get("HTTP_COOKIE")
    if raw_cookie:
        jar: SimpleCookie = SimpleCookie()
        try:
            jar.load(raw_cookie)
            cookies = {name: morsel.value for name, morsel in jar.items()}
        except Exception:  # noqa: BLE001 - a malformed cookie is simply absent
            cookies = {}
    headers = {
        key[5:].replace("_", "-").lower(): str(value)
        for key, value in environ.items()
        if key.startswith("HTTP_")
    }
    return Request(
        method=method, path=path, query=query, form=form, cookies=cookies, headers=headers
    )


class ThreadingWSGIServer(WSGIServer):
    """One thread per request, so a slow page never blocks the kill switch."""

    daemon_threads = True
    allow_reuse_address = True

    def process_request(self, request: Any, client_address: Any) -> None:  # noqa: ANN401
        thread = threading.Thread(
            target=self._handle_in_thread, args=(request, client_address), daemon=True
        )
        thread.start()

    def _handle_in_thread(self, request: Any, client_address: Any) -> None:  # noqa: ANN401
        try:
            self.finish_request(request, client_address)
        except Exception:  # noqa: BLE001 - reported by the base class's hook
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


class _QuietHandler(WSGIRequestHandler):
    """Access log without query strings or bodies: nothing an operator typed is logged."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ANN401
        del format, args


@contextmanager
def serve(
    app: Callable[..., Iterable[bytes]], *, host: str, port: int
) -> Iterator[ThreadingWSGIServer]:
    """A bound server for a `with` block; the caller runs `serve_forever`."""
    server = make_server(
        host, port, app, server_class=ThreadingWSGIServer, handler_class=_QuietHandler
    )
    try:
        yield server
    finally:
        server.server_close()
