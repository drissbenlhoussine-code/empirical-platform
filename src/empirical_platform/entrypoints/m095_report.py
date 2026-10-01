"""MILESTONE-095 -- `empirical-platform-event-report`: the read-only Owner event-driven-
edge-research report console.

    python -m empirical_platform.entrypoints.m095_report
    python -m empirical_platform.entrypoints.m095_report --port 8096

NO TRADING CONTROLS, NO BROKER CLIENT, NO PERSISTENCE. This process reads ONE already-
computed JSON file (`external-review/MILESTONE-095/event-study-results.json`, produced
entirely offline by `tools/m095_event_study.py`) at startup and serves it as a rendered
report on two GET routes. There is no POST route anywhere in this console, no CSRF token,
and no import of any broker adapter or usecase handler -- see
`tests/architecture/test_m095_report_boundaries.py`.

It binds to the loopback address only and refuses any other host, matching every other
console in this repository.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

from empirical_platform.entrypoints import _m095_report_html as html

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
#: Deliberately distinct from every other console in this repository (8086 SIMULATION,
#: 8189 M088/M089 PAPER, 8090 M090, 8092 M091, 8093 M092, 8094 M093, 8095 M094).
DEFAULT_PORT = 8096
DEFAULT_RESULTS_PATH = (
    Path(__file__).resolve().parents[3]
    / "external-review"
    / "MILESTONE-095"
    / "event-study-results.json"
)


def _loopback(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise SystemExit(
            f"REFUSED: --host must be a loopback IP address such as {DEFAULT_HOST}; got {host!r}"
        ) from error
    if not address.is_loopback:
        raise SystemExit(
            f"REFUSED: the event report console binds to the loopback address only; "
            f"{host!r} is not loopback. It must not be exposed beyond this machine."
        )
    return host


def _load_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"REFUSED: no results file at {path}. Run tools/m095_event_study.py first."
        )
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="loopback address to bind (default 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default 8096)")
    parser.add_argument(
        "--results",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help="path to the M095 event-study-results.json "
        "(default: external-review/MILESTONE-095/event-study-results.json)",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    arguments = parser.parse_args(argv)
    host = _loopback(arguments.host)
    results = _load_results(arguments.results)

    from wsgiref.simple_server import make_server

    from empirical_platform.entrypoints._operator_console_web import (
        Request,
        Response,
        Router,
        SecuritySession,
        ThreadingWSGIServer,
        html_response,
    )

    security = SecuritySession()
    router = Router(security)
    page = html.report_page(results)

    def report(request: Request, csrf: str) -> Response:
        del request, csrf
        return html_response(page)

    def stylesheet(request: Request, csrf: str) -> Response:
        del request, csrf
        body = html.STYLESHEET.encode("utf-8")
        return Response(
            "200 OK",
            [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(body)))],
            body,
        )

    router.get("/", report)
    router.get("/report", report)
    router.get("/static/event-report.css", stylesheet)

    server = make_server(
        host,
        arguments.port,
        router,
        server_class=ThreadingWSGIServer,
    )
    try:
        url = f"http://{host}:{server.server_port}/report"
        print("=" * 72)
        print("  M095 EVENT-DRIVEN EDGE RESEARCH REPORT -- READ ONLY. No trading controls here.")
        print(f"  Classification: {results['classification']}")
        print(f"  Open {url}")
        print("  Press Ctrl+C to stop.")
        print("=" * 72, flush=True)
        if not arguments.no_browser:
            webbrowser.open(url)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nm095-report: stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
