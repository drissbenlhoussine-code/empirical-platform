# Operator Console — runbook (MILESTONE-086, SIMULATION only)

The Operator Console is the daily screen over the trading engine: Today, Active trades,
History and Safety, in one local web page. In this milestone it runs against a deterministic
**simulated broker** only. No order can reach Alpaca or any other venue from it, no brokerage
credential is read, and nothing is exposed beyond this machine.

## Start

```
empirical-platform-operator-console
```

That is the whole command for normal use. It:

1. connects to the PostgreSQL database named by the usual `EMPIRICAL_PLATFORM_POSTGRES_*`
   variables (the same database the engine's commands use) and refuses to start unless the
   schema is at the exact MILESTONE-085 head;
2. binds to `http://127.0.0.1:8086` (loopback only; any other host is refused);
3. opens the browser on **Today**;
4. keeps asking the simulated broker about every open execution every few seconds, so
   Active trades moves from Submitted to Accepted to Filled on its own.

A large **SIMULATION** badge is on every page. Paper reads "Locked pending M085 Paper
Acceptance"; Live reads "Not authorized".

Useful options:

| Option | Meaning |
|---|---|
| `--load-day` | stage the deterministic simulation day at start (twelve symbols, one broker behaviour each) |
| `--reset-simulation` | make the simulated broker forget every order it received |
| `--no-browser` | do not open a browser |
| `--port 8090` | another port |
| `--state-dir PATH` | where the simulated broker keeps its memory (default `~/.empirical-platform/operator-console`) |
| `--reconcile-every 0` | turn the background broker check off (use "Check with broker now" instead) |

## Stop

Press `Ctrl+C` in the terminal that started it. The console stops taking requests, waits for the
background broker check to finish its current pass, and only then closes the database and releases
the state directory. Nothing needs to be flushed: every decision, authorization and execution is
already in PostgreSQL, and the simulated broker's memory is already on disk.

## One console at a time

Only one console may run on a state directory. A second start on the same `--state-dir` is
refused immediately with `REFUSED: another Operator Console already owns the simulation state
directory ...` (exit code 2) before it touches anything. Stop the first one, or use another
`--state-dir`. If a console crashes, the lock is released by the operating system; nothing needs
to be cleaned up.

## Restart and recovery

Start it again. The console rebuilds every page from the database and the simulated broker's
file; it keeps nothing of its own. Consequences you will notice, all intended:

- a confirmation page left open before the restart no longer works — the button says the page
  is out of date and nothing was done; open the opportunity again;
- an execution whose outcome was unknown when the process stopped is still "Needs attention"
  after the restart, and the background check resolves it from what the broker actually holds;
- refreshing any page never repeats an action.

## Database requirement

PostgreSQL 16, at the MILESTONE-085 schema head (`alembic upgrade head`). The console adds
no tables: the simulated broker's memory is a JSON file under `--state-dir`, not a migration.

## Simulation reset and fixture load

- `--load-day` stages the day: saves the simulation trading configuration `CFG-086-SIM` (long
  only, whole shares, no leverage, no overnight, 2 000 USD per trade, 60 s quote freshness, 1 %
  spread limit), opens an evaluation context and asks the real MILESTONE-084 handler to
  propose one candidate per staged symbol. Loading the same day twice creates nothing new.
- The **Load simulation day** button on an empty Today does the same.
- `--reset-simulation` clears the simulated broker's orders. It does not touch PostgreSQL: the
  engine's records are the engine's.
- To start a completely fresh day, use a fresh database (the engine's own disposable-database
  procedure) and `--reset-simulation`.

Staged behaviours, by symbol (shown under each card's *Details*):

| Symbol | Simulated broker behaviour |
|---|---|
| AAPL | accepted, then filled |
| MSFT | accepted, then partially filled |
| NVDA | accepted, never filled |
| AMZN | rejected by the broker |
| GOOGL | delivered, but the answer is lost (outcome unknown, then found) |
| META | network failure before anything is sent |
| JPM | network failure after the request may have been delivered |
| V | cancel succeeds |
| JNJ | cancel requested, but the order fills first |
| PG | reconciliation finds the order |
| XOM | the request is lost; reconciliation never finds it |
| KO | outcome unknown across a restart |

## What the screens mean

- **Needs decision** — the engine proposed it; approve or reject. **Approve** opens a
  confirmation with the exact terms; only **CONFIRM APPROVAL** does anything.
- **Blocked** — nothing was sent (kill switch, a refused check, or a failure before the send).
- **Needs attention** — outcome unknown, do not retry. The console keeps checking the same
  order and never sends it again.
- **Filled / Partially filled** — an **open position**. It stays on Active trades with its exit
  shown as *locked pending M087*: this milestone has no exit path, so nothing can be sent for it.
- **Approved / Submitted / Accepted / Cancel requested / Cancelled / Rejected / Expired** — the
  engine's own state, in plain words. Anything the engine does not
  know shows as **Not available**, never as a guess.

## Safety page

Shows the environment badge, the execution kill switch with **ACTIVATE** / **DEACTIVATE**
(each behind a confirmation), and the trading rules read from the configuration the engine
uses. While the kill switch is engaged, no approval can be confirmed and every pending card says
so; existing executions remain visible and keep being reconciled.
