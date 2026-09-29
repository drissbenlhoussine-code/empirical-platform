# MILESTONE-089 — PAPER SELL_TO_CLOSE architecture: Store B, Store C, and the link between them

Status: ENGINEERING. No real Paper BUY or SELL has been submitted for this milestone. See
`scope-and-design.md` for the acceptance contract this document implements.

## 1. Three stores, never a shared transaction

| Store | Database | Owner | What lives there | Schema authority |
|---|---|---|---|---|
| A | `empirical_platform` (or whatever `EMPIRICAL_PLATFORM_POSTGRES_DATABASE` names for a SIMULATION process) | M085/M086/M087 | SIMULATION entry + SIMULATION exit | `require_exact_m087_schema_head` → `e7c1a9d3b5f2` |
| B | `empirical_platform_paper` | M085/M088 | The real Alpaca-Paper-bound entry lifecycle (`paper_execution_attempt` and its siblings) | `require_exact_m085_schema_head` → `a7d3c9e14f26`, **pinned, never migrated forward by this milestone** |
| C | `empirical_platform_paper_exit` (or `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE`) | M089 (new) | The PAPER exit lifecycle: `position_exit_preview`/`_authorization`/`_attempt`/`_acknowledgement`/`_reconciliation_round`/`_event`, `environment = 'PAPER'` | `require_exact_m089_schema_head` → `f083b6c29d17` (`shared/persistence/postgres_repositories/paper_position_exit_schema.py`) |

Store C runs its **own, self-contained Alembic chain** (`alembic_paper_exit.ini`,
`migrations_paper_exit/`, one revision, `down_revision = None`). It is never reachable from the
`migrations/` chain `alembic.ini` points at, and that chain is never reachable from Store C's:
pointed at a fresh database, `alembic upgrade head` under either `.ini` creates only the objects
its own chain owns. This is why Store C can be created and migrated without ever touching, or
being able to touch, the M082–M087 objects that live in Store A and Store B.

**No cross-database transaction is ever assumed atomic.** A preview is built by reading Store B
live and is saved to Store C as a separate operation; an authorization consumption and an
attempt-claim are atomic WITHIN Store C (the same `claim_dispatch` guarantee M087 already proved,
reused unchanged); nothing spans both databases in one commit. Where M087's Store-A migration
used a same-database `BEFORE INSERT` trigger (`position_exit_preview_guard_insert`) to re-check a
preview's entry evidence against `paper_execution_attempt` at INSERT time, Store C's migration has
no such trigger — that table does not exist there — and the check moves to the one place that
already re-reads Store B on every relevant step: `usecases.position_exit`.

## 2. The link: entry intent → attributable PAPER position → exit request

Nothing new was written for this. `usecases.position_exit.AssessPositionExitHandler` and
`PreviewPositionExitHandler` (M087, unmodified) already take `intents` and `entry_attempts` as
injected repositories — Protocol-typed, storage-neutral — and M089's only change to the domain
layer was widening `ALLOWED_EXIT_ENVIRONMENTS` to include `PAPER`
(`decision_candidate/position_exit.py`). `entrypoints/_paper_position_exit_composition.py` wires:

```
intents        = Store B .m084.approved_order_intents      (the M084/M085 approved intent)
entry_attempts = Store B .paper.execution_attempts          (the real Alpaca Paper entry fill)
exit_attempts / previews / authorizations / ... = Store C   (PostgresPositionExitRuntime)
broker / market_data = Store B's real AlpacaPaperClient / AlpacaPaperMarketDataClient
```

`AssessPositionExitHandler.handle(entry_intent_governance_id, at=...)`:

1. Reads the approved intent from Store B (`intents.get`) — refuses if absent.
2. Reads the M085 entry attempt for that intent from Store B (`entry_attempts.for_intent`).
3. Reads every OTHER exit attempt ever made for this entry from Store C
   (`exit_attempts.for_entry`) and sums their filled quantity — `exits_filled_quantity`.
4. Reads the CURRENT broker position for the symbol with a fresh `broker.fetch_position(symbol)`
   call — never a cached or earlier-observed value.
5. Scans Store B's recent entry attempts for `competing_entry_attempt_ids`: any OTHER entry in
   the same symbol that still holds shares and has no exit that closed it — attribution is
   refused as ambiguous when this is non-empty (Phase 4's "fail closed if attribution is
   ambiguous", unchanged from M087).
6. Builds one `PositionSnapshot` from steps 2–5, all captured at the SAME instant `at`, and runs
   the pure `exit_eligibility(snapshot, existing_exit=...)` rule over it.

`PositionSnapshot.attributable_quantity` is `entry_filled_quantity − exits_filled_quantity` when
both are proven whole numbers and the result is positive; otherwise `None`, and `None` is a
refusal, never a guess. `exit_eligibility` additionally requires the entry to be FILLED (or
CANCELED with a proven filled part), the broker's own current position to equal the attributable
quantity exactly, no competing entry, and no exit already open or filled for this entry. **This
is where "do not infer ownership merely because Alpaca says quantity > 0" is enforced**: the
broker's position is CONSULTED, but the request's quantity, symbol and identity all come from the
Store-B entry record; a broker balance with no matching Store-B entry, or a Store-B entry whose
filled quantity does not equal what the broker currently shows, is refused, not adopted.

`PreviewPositionExitHandler.handle` then re-runs the assessment (so the preview is built from a
FRESH read, not a stale one), and only when eligible constructs `PositionExitRequest` (quantity =
`snapshot.attributable_quantity`, exactly) and `PositionExitPreview`. `PositionExitPreview.__post_init__`
independently re-derives the full-close arithmetic and the request fingerprint in pure Python — a
second, storage-independent check that a caller cannot bypass by skipping the live read, because
the object simply cannot be constructed otherwise (`ValueError`).

## 3. What moved, in file terms

| Change | File | Nature |
|---|---|---|
| `ALLOWED_EXIT_ENVIRONMENTS` widened to `{SIMULATION, PAPER}` | `decision_candidate/position_exit.py` | One frozenset literal + docstring |
| `submit_close_order` implemented | `shared/brokerage/alpaca_paper.py` | New method, narrow: takes only `PositionExitRequest`, mirrors `submit_order`'s exactly-once/ambiguity/redirect-refusal/acknowledgement-validation discipline |
| Store C schema | `migrations_paper_exit/`, `alembic_paper_exit.ini` | New, self-contained chain, one revision |
| Store C schema-head guard | `shared/persistence/postgres_repositories/paper_position_exit_schema.py` | New module; `M087_SCHEMA_HEAD`/`require_exact_m087_schema_head` (Store A) untouched |
| Dual-store composition | `entrypoints/_paper_position_exit_composition.py` | New; imports M088's `PAPER_CAPABILITY`/`PaperConsoleBackend` unchanged; never imports/modifies `paper_operator_console_runtime` |
| CLI | `entrypoints/operator_console.py` | New `--capability paper-exit` choice; `--capability paper` (M088) byte-identical in behavior |
| Capability-aware wording | `usecases/operator_console_exits.py`, `entrypoints/_operator_console_html.py`, `entrypoints/operator_console_app.py` | M087 hardcoded "(simulation)"/"simulated broker"/a literal `"Simulation"` capability-label bug fixed; SIMULATION wording unchanged byte-for-byte |
| Exit review page fields | `usecases/operator_console_exits.py` (`ExitReviewView`) | Added `position_captured_at`, `client_order_id`, `full_close_warning` (Phase 5) |

`usecases/position_exit.py` (Assess/Preview/Authorize/Submit/Reconcile/Cancel), the six exit
Postgres repository classes, and `usecases/operator_console.py`'s `OperatorConsoleService` core
were **not modified** by this milestone beyond the capability check M088 already widened to
`{SIMULATION, PAPER}`. Reuse, not rewrite, is the design.

## 4. Kill switch — preserved doctrine, not a new decision (Phase 11)

M087's own README already states the rule this milestone reuses verbatim: *"The M085 execution
stop is READ, not reinterpreted: engaged → authorization and submission refused with 'release it
on the Safety page first'; review page shows the banner."* `AuthorizePositionExitHandler` and
`SubmitAuthorizedPositionExitHandler` (both unmodified) call `self._kill_switch.is_engaged()`
unconditionally, with no environment branch and no bypass path. For PAPER, the kill switch this
milestone reads is Store B's own `execution_kill_switch` — the SAME kill switch M088's PAPER entry
console already reads and that a real Owner would engage from the Safety page. There is **no
emergency/position-reducing bypass** anywhere in this codebase: engaging the kill switch blocks a
new exit exactly as it blocks a new entry. This is reported as the existing, tested, unambiguous
doctrine — nothing was invented or silently decided for this milestone.

## 5. What Store C's migration deliberately does NOT reproduce from M087's

Only the `position_exit_preview_guard_insert` trigger (same-database validation against
`paper_execution_attempt`) is absent, and only because that table has no counterpart in Store C.
Every other guard — the authorization/attempt/round insert-and-update triggers, the partial unique
index enforcing at most one active exit per position, the append-only triggers on preview/
authorization/acknowledgement/round/event, and every CHECK constraint — is reproduced verbatim,
adjusted only for `environment = 'PAPER'` in place of `'SIMULATION'`.
See `tests/architecture/test_m089_paper_exit_boundaries.py` and
`tests/integration/test_m089_paper_exit_postgres.py` for the machine-checked proof.
