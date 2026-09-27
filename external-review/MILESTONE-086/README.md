# MILESTONE-086 — Operator Console, daily decision UI and safe simulation

Status: **M086 SIMULATION CANDIDATE — OWNER REVIEW REQUIRED.** Local commits only; not pushed,
not merged, not frozen. **No Alpaca call of any kind, no Paper order, no live trading.** The only
execution capability the console can be composed for is SIMULATION; Paper is displayed as
"Locked pending M085 Paper Acceptance" and Live as "Not authorized". M085 Paper Acceptance
remains NOT_STARTED and is deferred until the US market is open. M085 is consumed, not changed:
no M085 handler, repository, migration, trigger, state machine or authority file is modified.

Verification for the exact candidate SHA: [verification.md](verification.md). Screens captured
from the running console: `screens/`. Runbook: `docs/operations/operator-console.md`.

## 1. What M086 establishes

One local web application (`empirical-platform-operator-console`, bound to 127.0.0.1) through
which the Owner can, in SIMULATION:

1. see today's opportunities (Today) with the exact proposed trade, quantity, notional, the
   capital cap, stop and target, risk, the reason and the evidence summary;
2. approve in two stages — APPROVE opens a confirmation of the immutable terms, only CONFIRM
   APPROVAL acts — or reject with one confirmation;
3. follow every execution (Active trades) with a timeline that shows only steps the durable
   record proves; UNKNOWN stays "Needs attention — do not retry";
4. review a searchable history that distinguishes the model proposal, the Owner decision, the
   simulation execution, and Broker/Paper execution (future only);
5. engage or release the execution kill switch (Safety), each behind a confirmation, and read
   the trading rules from the configuration the engine uses;
6. run the whole day — research fixture → proposal → decision → intent → authorization →
   dispatch → accepted → filled → history — with zero broker traffic.

## 2. What M086 does NOT establish

- Any Paper or live execution. There is no LIVE implementation; the composition root refuses
  every capability but SIMULATION and does not import the Alpaca client.
- That simulated fills, prices or the staged quotes say anything about a market.
- Profit and loss: History shows "Not available" wherever the platform records no result.
- Exits: M085 has no sell path; a filled simulated order is recorded as a held position.
- Multi-user or remote use: one operator, loopback only, one process.

## 3. Architecture (chosen stack and why)

```
Browser  →  entrypoints/operator_console_app.py (routes) + _operator_console_html.py (pages)
            + _operator_console_web.py (WSGI, CSRF, headers, loopback server)
         →  usecases/operator_console.py (application services, human vocabulary, tickets)
            + usecases/operator_console_fixtures.py (the simulation day)
         →  existing M084/M085 usecases and repository protocols
         →  PostgreSQL (M085 schema head a7d3c9e14f26)     +  shared/brokerage/simulation_paper.py
entrypoints/_operator_console_composition.py  ← the only place a broker is built (SIMULATION only)
entrypoints/operator_console.py               ← the one command
```

**Python standard library only, no new dependency.** A local single-operator console needs
routing, forms, cookies, a CSRF token, security headers and a threaded local server; all of that
is in `wsgiref`, `http.cookies`, `urllib.parse`, `hmac` and `secrets`. A web framework would
have added several third-party packages and their audit surface to carry seven pages. Business
logic stays where it is: the console requests actions from M084/M085 handlers and never writes
an execution table; a route imports no persistence, broker or domain module (architecture test).

## 4. Safety boundaries, stated

- **Capability firewall.** `ExecutionCapability` is decided by the composition root. Every
  state-changing request is screened by `refuse_requested_environment`: any `environment`,
  `capability`, `mode` or `venue` field — even `SIMULATION` — is refused with 403 and nothing runs.
- **No bypass of M085.** CONFIRM APPROVAL runs the existing chain: paper-bound decision →
  paper-bound intent → submission preview → human authorization bound to the preview's request
  fingerprint (the preview's order must equal the terms shown, or nothing is authorized) →
  `SubmitAuthorizedPaperOrderHandler`. Reconciliation and cancellation are the M085 handlers.
- **Stale state never executes.** The confirmation ticket is HMAC-signed by the process and
  binds the action, proposal id, version, content fingerprint and issue time; the service
  re-reads the proposal and refuses when it changed, expired, was decided, or when the kill
  switch is engaged. A restart invalidates every open ticket.
- **Idempotent by derivation.** Decision, intent, preview, authorization and attempt ids are
  derived from the proposal id; a duplicated request (refresh, retry, second tab) resumes at the
  first row that exists and reports the existing execution. POSTs answer 303, so a browser
  refresh never re-submits.
- **Honest states.** Twelve human words map one-to-one onto the engine's states; UNKNOWN is
  "Needs attention"; a failure before the send is "Blocked"; every message says either
  "Nothing was sent" or "Outcome unknown — do not retry".
- **Kill switch.** The M085 execution stop through its own handler. While engaged: no approval
  can be confirmed, cards say so, existing executions stay visible and keep being reconciled.
- **Web security.** Loopback only (non-loopback hosts refused before anything starts), CSRF
  token = HMAC(process secret, session cookie) with HttpOnly SameSite=Strict, CSP
  `default-src 'none'` with one same-origin stylesheet, no script, no inline style, no
  third-party asset, no credential anywhere (none exists in the process), 64 KiB body limit,
  no query strings or bodies in the access log.

## 5. The simulation

`SimulatedPaperBroker` implements the M085 broker and market-data ports over a durable JSON
store (atomic replace), so an ambiguous dispatch survives a restart the way a real broker's
memory does. Twelve staged behaviours, one per symbol, cover: accepted+filled, accepted not
filled, partial fill, broker rejection (a documented definitive refusal code), ambiguous
submission, network failure before send (nothing recorded), network failure after a possible
send (recorded, answer lost), cancel success, cancel/fill race, reconciliation finds the order,
reconciliation never finds it (resolved only by M085's bounded absence policy), and restart
while unknown. Simulated evidence is marked wherever a domain type allows it (`sim-` order ids,
`SIMULATION-ACCOUNT-0001`, `"simulation": true` payloads, `SIMULATION` quote source,
`simulation.invalid` market-data host). Two domain invariants leave no room and are stated
plainly: the account snapshot's `endpoint_host` must equal the pinned paper host and
`PaperEnvironment` has only PAPER; the console's badge comes from the composition's capability,
never from broker evidence.

The simulation day is loaded through the real M084 paper-bound proposal handler from fixture
inputs marked `SIMULATION`. Because the engine rightly refuses a proposal whose mandatory
liquidation is unreachable late in the operator's day, the fixture places the operator's day in a
fixed-offset zone where "now" is mid-morning, recording a new configuration version (never an
edit) when the zone must move.

## 6. Adversarial self-review

| Attack | Result |
|---|---|
| Direct HTTP POST bypassing confirmation | Refused: no valid ticket → 400, nothing decided (test) |
| Refresh / double click / retry approves twice | 303 after POST; second confirmation reports "Already confirmed"; one order (tests, browser run) |
| Two tabs approve twice | Second tab's ticket finds the existing attempt; one order (test) |
| Expired or stale proposal executes | Ticket re-read: expired → refused; version/fingerprint changed → "Terms changed" (tests) |
| Browser chooses PAPER/LIVE | Any environment field → 403, nothing runs; composition refuses PAPER/LIVE (tests) |
| Kill switch loses a race | Checked at confirmation AND by M085 preview/dispatch; engaged just before confirm → refused, no attempt (unit + PostgreSQL) |
| UI shows FILLED when persistence says UNKNOWN | State word is a pure function of the durable attempt; UNKNOWN → Needs attention (tests) |
| Restart manufactures an action | Restart reconstructs from repositories and the store; old tickets refused; refresh sends nothing (unit + PostgreSQL) |
| Exception leaks a secret | No credential exists; unexpected errors render a generic page, never a traceback (test); access log carries no bodies |
| Simulation confused with broker evidence | Marked ids/payloads/source/host; execution kind "Simulation execution" in Active and History; badge from capability |
| Active trades hides an unresolved order | Every non-terminal attempt is listed; UNKNOWN is flagged with a danger note (tests) |
| History mutates past decisions | History is read-only; no route writes proposals, decisions or intents; M084 repositories refuse a second decision/intent |
| Mobile layout hides safety information | Badge, kill-switch banner and status chips stay in the flow at phone width; no horizontal scroll rule; rendering contract tested. Real phone-width screenshots could not be taken with the available browser tooling (window minimum width); the layout is exercised by the CSS media query and the contract test only |

Findings fixed during the review: (1) the simulation day was refused wholesale late in the UTC
day (`LIQUIDATION_DEADLINE_UNREACHABLE`) — fixed by the operator-day placement above, not by
weakening the rule; (2) filled quantities rendered as `8.00000000` — whole shares now read as
whole numbers; (3) the launcher initially contained an unreachable shutdown expression — removed.

## 7. Known limitations (real)

- **The M085 exhaustion table now derives 30/31.** Its row 30, "No M086 path exists", is
  MILESTONE-085's own scope guard (any tracked path matching `m086|MILESTONE-086`, in
  `tools/render_m085_exhaustion_table.py`). The Owner's M086 mission proceeds while M085 Paper
  Acceptance is deferred, so that row now reports a blocker by design and the table is rendered
  honestly as **30 of 31, 1 blocker** (commit `9af6577`; the message of that commit predicted
  "31/31" and is superseded by this note). The M085 renderer was deliberately not modified —
  it is M085 content and a gate. Resolving row 30 is an Owner decision: ratify a scoped
  exception for the M086 paths in the M085 table, or keep the blocker visible until M085 Paper
  Acceptance closes.
- Phone-width screenshots are absent (tooling), see above.
- The background reconciler is a thread in the console process; if the console is not running,
  nothing reconciles until it is started again or "Check with broker now" is pressed.
- The confirmation flash message is held in process memory; a restart drops it (the durable
  state is still shown).
- Positions are counted from filled attempts; there is no exit path in M085.
- `--load-day` with an existing configuration whose watchlist lacks a symbol will have that
  symbol refused by the engine (reported, not forced).
