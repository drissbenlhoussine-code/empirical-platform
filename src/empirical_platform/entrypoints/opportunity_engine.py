"""MILESTONE-090 -- `empirical-platform-opportunity-engine`: start the Opportunity Engine console.

    empirical-platform-opportunity-engine
    empirical-platform-opportunity-engine --no-browser --port 8095

RESEARCH + ENGINEERING ONLY. Every route this console serves is read-only or records an Owner
decision durably (APPROVE/IGNORE) -- none of them can place, modify or cancel an order. See
`entrypoints._opportunity_engine_composition`'s module docstring for exactly what this process
constructs and why it can never reach a broker write. There is no `--capability` flag: this
console always reads real Alpaca PAPER market data (quotes, clock, asset lookups, minute bars)
for its evaluation, but never submits anything -- unlike `operator_console.py`, "paper" here
describes the market-data feed's authenticity, never a trading capability.

It binds to the loopback address only and refuses any other host, matching every other console
in this repository.

`--base-path` (default: none, i.e. root behaviour, unchanged) declares the path prefix this
process is reverse-proxied under, e.g. `--base-path /m090-review` behind
`tailscale serve --set-path /m090-review http://127.0.0.1:PORT`. It never changes what this
process binds to or listens on -- only the URLs it generates in its own pages.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
import webbrowser

from empirical_platform.entrypoints import _opportunity_engine_html as html
from empirical_platform.entrypoints._operator_console_web import SecuritySession, serve
from empirical_platform.entrypoints._opportunity_engine_composition import (
    opportunity_engine_runtime,
)
from empirical_platform.entrypoints.opportunity_engine_app import (
    build_opportunity_engine_application,
)

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
#: Deliberately distinct from SIMULATION (8086) and the M088/M089 PAPER console (8189).
DEFAULT_PORT = 8090


def _loopback(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise SystemExit(
            f"REFUSED: --host must be a loopback IP address such as {DEFAULT_HOST}; got {host!r}"
        ) from error
    if not address.is_loopback:
        raise SystemExit(
            f"REFUSED: the Opportunity Engine console binds to the loopback address only; "
            f"{host!r} is not loopback. It must not be exposed beyond this machine."
        )
    return host


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="loopback address to bind (default 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default 8090)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument(
        "--base-path",
        default="",
        help="path prefix this console is reverse-proxied under, e.g. /m090-review (default: none)",
    )
    arguments = parser.parse_args(argv)
    host = _loopback(arguments.host)
    try:
        base_path = html.validate_base_path(arguments.base_path)
    except ValueError as error:
        raise SystemExit(f"REFUSED: {error}") from error

    with opportunity_engine_runtime() as backend:
        application = build_opportunity_engine_application(
            backend, security=SecuritySession(), base_path=base_path
        )
        with serve(application, host=host, port=arguments.port) as server:
            # Direct/local URL is always unprefixed: THIS process only ever registers
            # unprefixed routes (a reverse proxy strips base_path before forwarding here, it
            # never reaches this process). base_path only shapes the URLs this process itself
            # generates inside its own pages, for whatever proxy sits in front of it.
            local_url = f"http://{host}:{server.server_port}/today"
            print("=" * 72)
            print("  OPPORTUNITY ENGINE -- RESEARCH ONLY. No order can be placed from here.")
            print("  Owner APPROVE/IGNORE is recorded durably; nothing downstream acts on it.")
            print(f"  Open (direct/local): {local_url}")
            if base_path:
                print(f"  Configured base path for a reverse proxy: {base_path}")
            print("  Press Ctrl+C to stop.")
            print("=" * 72, flush=True)
            if not arguments.no_browser:
                webbrowser.open(local_url)
            try:
                server.serve_forever(poll_interval=0.5)
            except KeyboardInterrupt:
                print("\nopportunity-engine: stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
