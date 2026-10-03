"""Read-only Owner connectivity probe. No database or order capability is constructed."""

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime

from empirical_platform.usecases.market_console import market_status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, help="explicit Paper DU account identifier")
    parser.add_argument("--client-id", type=int, default=71)
    parser.add_argument("--port", type=int, choices=(7497, 4002), default=7497)
    parser.add_argument("--symbol", required=True, help="Owner-selected Helsinki equity")
    args = parser.parse_args(argv)
    try:
        from empirical_ibkr.paper import IBKRPaperAdapter
        from empirical_ibkr.session import IBKRSession
    except ImportError:
        print(
            json.dumps(
                {
                    "status": "IBKR_OWNER_SETUP_REQUIRED",
                    "reason": "install the optional integration and official TWS API SDK",
                }
            )
        )
        return 2
    session = None
    try:
        session = IBKRSession(account=args.account, port=args.port, client_id=args.client_id)
        session.connect()
        adapter = IBKRPaperAdapter(session)  # Write capability remains disabled.
        contract = adapter.resolve(args.symbol)
        account = adapter.account()
        positions = adapter.positions()
        orders = adapter.open_orders()
        result: dict[str, object] = {
            "status": "READ_ONLY_CONNECTION_VERIFIED",
            "broker": "IBKR_PAPER",
            "account_reference": account.identity.reference,
            "account_ready": account.ready,
            "instrument_fingerprint": contract.instrument.fingerprint,
            "conid": contract.instrument.contract_id,
            "symbol": contract.instrument.symbol,
            "venue": contract.instrument.venue,
            "exchange": contract.instrument.exchange,
            "currency": contract.instrument.currency.value,
            "positions": len(positions),
            "open_orders": len(orders),
            "calendar": dict(market_status(datetime.now(UTC)))["Exchange calendar"],
            "database_guards": "NOT_CHECKED_BY_CONNECTIVITY_PROBE",
            "broker_writes": 0,
        }
        if result["calendar"] == "OPEN":
            quote = adapter.quote(contract.instrument)
            quote.validate(contract.instrument, datetime.now(UTC), 30)
            result["bid"], result["ask"] = str(quote.bid), str(quote.ask)
            result["quote_at"] = quote.source_at.isoformat()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Do not echo SDK payloads, account details, server text, or credentials.
        print(
            json.dumps(
                {
                    "status": "IBKR_OWNER_SETUP_REQUIRED",
                    "reason_type": type(error).__name__,
                    "next_step": (
                        "verify Paper login, API permission, client ID "
                        "and Helsinki live-data entitlement"
                    ),
                    "broker_writes": 0,
                }
            )
        )
        return 2
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
