"""MILESTONE-086 -- `empirical-platform-operator-console`: start the Operator Console.

    empirical-platform-operator-console                 # serve on http://127.0.0.1:8086 and open it
    empirical-platform-operator-console --load-day      # also stage the simulation day at start
    empirical-platform-operator-console --no-browser --port 8090

SIMULATION ONLY. The console composes the deterministic simulated broker and nothing else;
no Alpaca credential is read and no order can reach any venue. It binds to the loopback
address and refuses any other host. One process serves the pages and, in the background,
asks the simulated broker about every open execution through the MILESTONE-085 reconciler,
so Active trades moves from Submitted to Accepted to Filled without shell interaction.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
import threading
import webbrowser
from pathlib import Path

from empirical_platform.entrypoints._operator_console_composition import (
    simulation_console_runtime,
)
from empirical_platform.entrypoints._operator_console_web import SecuritySession, serve
from empirical_platform.entrypoints.operator_console_app import build_application

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8086
DEFAULT_STATE_DIR = Path.home() / ".empirical-platform" / "operator-console"


def _loopback(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise SystemExit(
            f"REFUSED: --host must be a loopback IP address such as {DEFAULT_HOST}; got {host!r}"
        ) from error
    if not address.is_loopback:
        raise SystemExit(
            f"REFUSED: the Operator Console binds to the loopback address only; {host!r} is not "
            "loopback. It must not be exposed beyond this machine."
        )
    return host


class _Reconciler(threading.Thread):
    """Ask the broker about open executions every few seconds, until stopped."""

    def __init__(self, refresh: object, interval: float) -> None:
        super().__init__(name="operator-console-reconciler", daemon=True)
        self._refresh = refresh
        self._interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._refresh()  # type: ignore[operator]
            except Exception as error:  # noqa: BLE001 - keep reconciling; the handler recorded it
                print(
                    f"operator-console: reconciliation pass failed: {type(error).__name__}",
                    file=sys.stderr,
                )

    def stop(self) -> None:
        self._stop.set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="loopback address to bind (default 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default 8086)")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="where the simulated broker keeps its durable state "
        "(default ~/.empirical-platform/operator-console)",
    )
    parser.add_argument(
        "--load-day", action="store_true", help="stage the deterministic simulation day at start"
    )
    parser.add_argument(
        "--reset-simulation", action="store_true", help="forget the simulated broker's orders first"
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument(
        "--reconcile-every",
        type=float,
        default=5.0,
        help="seconds between background reconciliation passes (0 disables)",
    )
    arguments = parser.parse_args(argv)
    host = _loopback(arguments.host)

    with simulation_console_runtime(state_dir=arguments.state_dir) as runtime:
        if arguments.reset_simulation:
            runtime.store.reset()
        if arguments.load_day:
            report = runtime.load_day()
            print(
                f"simulation day {report.day}: proposed {', '.join(report.proposed) or 'nothing'}; "
                f"already present {', '.join(report.already_present) or 'nothing'}"
            )
        application = build_application(runtime, security=SecuritySession())
        reconciler = None
        if arguments.reconcile_every > 0:
            reconciler = _Reconciler(runtime.service.refresh_executions, arguments.reconcile_every)
            reconciler.start()
        with serve(application, host=host, port=arguments.port) as server:
            url = f"http://{host}:{server.server_port}/today"
            print("=" * 72)
            print("  OPERATOR CONSOLE -- SIMULATION ONLY. No order can reach any venue.")
            print(f"  Open {url}")
            print("  Paper execution locked -- acceptance pending. Live -- not authorized.")
            print("  Press Ctrl+C to stop.")
            print("=" * 72, flush=True)
            if not arguments.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever(poll_interval=0.5)
            except KeyboardInterrupt:
                print("\noperator-console: stopping")
            finally:
                if reconciler is not None:
                    reconciler.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
