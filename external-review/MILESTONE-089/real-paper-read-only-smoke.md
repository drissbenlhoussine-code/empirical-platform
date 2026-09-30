# MILESTONE-089 Phase 14 — real Alpaca Paper read-only smoke test

Run 2026-09-29 against the real `paper-api.alpaca.markets` endpoint (proven via
`PaperEndpoint.from_url`, which refuses anything else), using `AlpacaPaperClient`'s existing
read-only methods only. **No write method (`submit_order`, `submit_close_order`,
`cancel_order`) was called or imported into the smoke script.** BUY submissions = 0, SELL
submissions = 0, cancels = 0.

| Call | Result |
|---|---|
| `fetch_account()` | HTTP 200, account present, `status=ACTIVE` |
| `fetch_clock()` | `is_open=False`, `timestamp=2026-09-29T04:06:51Z`, `next_open=2026-09-29T09:30:00-04:00`, `next_close=2026-09-29T16:00:00-04:00` |
| `fetch_position("AAPL")` | `None` — no open Paper position (consistent with the M085 acceptance run: CANCELED, unfilled, zero position) |
| `fetch_asset("AAPL")` | `status=active`, `tradable=True`, `asset_class=us_equity`, `exchange=NASDAQ` |
| `fetch_quote("AAPL")` (market data) | bid `323.44` / ask `357.77`, `captured_at=2026-09-28T20:00:00Z`, `source=alpaca-iex` |
| `fetch_order_by_client_order_id("m085-113dd0e32c4d03438f7619afb3eac3d96e651ef8")` | HTTP 200, `broker_order_id=9e9a3a5d-cfd6-44f3-a6fd-88475c4cee08`, `status=canceled`, `symbol=AAPL`, `side=buy`, `quantity=1`, `filled_quantity=0`, `limit_price=4` — matches `external-review/MILESTONE-085/paper-acceptance-results.md` exactly |

No Paper position was created to test this milestone's engineering. This run used the SAME
credentials and endpoint `tools/m085_paper_acceptance.py` and the M088 Paper console use; it did
not touch Store B's or Store C's databases (no persistence call was made).
