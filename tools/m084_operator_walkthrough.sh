#!/usr/bin/env bash
# MILESTONE-084 -- the operator walkthrough, run against an INSTALLED WHEEL.
#
#   EMPIRICAL_PLATFORM_POSTGRES_PASSWORD=... bash tools/m084_operator_walkthrough.sh
#
# Everything here runs through console scripts from a wheel installed into a
# throwaway virtualenv, never from the source tree. That is the point. A
# walkthrough executed with `python -m` against `src/` proves the source works,
# which is not the question an operator is asking. Packaging defects -- an
# unregistered entry point, a module left out of the wheel, a dependency that
# only ever existed in the dev environment -- are invisible from the source tree
# by construction, and this script found one on its first run: the base install
# has no SQLAlchemy, because persistence is an optional extra.
#
# The database is rebuilt from nothing through the full migration history, so
# the walkthrough demonstrates the clean-database regression mode rather than
# describing it.
#
# Steps 13-15 are NO_TRADE demonstrations. A walkthrough that only shows the
# happy path documents a product that always says yes, and everything valuable
# about this one is in the cases where it says no.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="${M084_WALKTHROUGH_DIR:-/tmp/m084-walkthrough}"
VENV="$SCRATCH/venv"
WORK="$SCRATCH/work"
DB="empirical_walkthrough"
BIN="$VENV/bin/empirical-platform"

# 2026-06-10 12:00Z is 15:00 in Europe/Helsinki: inside the configured entry
# window and before the 15:45 mandatory liquidation.
AT="2026-06-10T12:00:00+00:00"
OBSERVED="2026-06-10T11:59:55+00:00"

export EMPIRICAL_PLATFORM_POSTGRES_DATABASE="$DB"
: "${EMPIRICAL_PLATFORM_POSTGRES_PASSWORD:?set EMPIRICAL_PLATFORM_POSTGRES_PASSWORD}"

STEP=0
FAILED=0

step() { STEP=$((STEP + 1)); printf '\n=== STEP %02d — %s\n' "$STEP" "$1"; }

# A step that expects a refusal is as much a pass as one that expects success.
# Accepting "0 or nonzero, either is fine" would make the walkthrough
# unfalsifiable, which is the failure mode it exists to avoid.
run() {
  local expect="$1"; shift
  echo "\$ $(basename "$1") ${*:2}"
  local output rc
  output="$("$@" 2>&1)"; rc=$?
  echo "$output" | sed 's/^/  /'
  if [ "$rc" != "$expect" ]; then
    echo "  !! expected exit $expect, got $rc"
    FAILED=$((FAILED + 1))
  fi
}

fatal() { echo "PREPARATION FAILED: $1" >&2; exit 2; }

# ---------------------------------------------------------------------------
# Preparation. These abort rather than letting fifteen steps fail downstream
# for one upstream reason.
# ---------------------------------------------------------------------------

rm -rf "$SCRATCH"; mkdir -p "$WORK"

echo "=== PREPARATION"
rm -rf "$REPO_ROOT/dist"
( cd "$REPO_ROOT" && .venv313/bin/python -m build --wheel >/dev/null 2>&1 ) \
  || fatal "wheel build"
WHEEL="$(ls "$REPO_ROOT"/dist/*.whl 2>/dev/null | head -1)"
[ -n "$WHEEL" ] || fatal "no wheel produced"
echo "  built $(basename "$WHEEL")"

# The project's own interpreter: the wheel requires >=3.13, and a bare `python3`
# on PATH here is 3.11. The first version of this script used `python3`, the
# install failed, and every step reported "command not found" -- honest, but a
# preparation failure should stop rather than be diagnosed fifteen times.
"$REPO_ROOT/.venv313/bin/python" -m venv "$VENV" || fatal "venv"
"$VENV/bin/pip" install -q "${WHEEL}[persistence]" >/dev/null 2>&1 \
  || fatal "wheel install"

"$VENV/bin/python" -c "
import empirical_platform, pathlib, sys
location = pathlib.Path(empirical_platform.__file__).resolve()
if 'site-packages' not in str(location):
    sys.exit('imported from the source tree, not the wheel: ' + str(location))
print('  running from', location.parent)
" || fatal "the wheel is not what is being exercised"

sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $DB" \
                     -c "CREATE DATABASE $DB OWNER empirical" >/dev/null 2>&1
( cd "$REPO_ROOT" && .venv313/bin/python -m alembic upgrade head 2>&1 |
  grep -c 'Running upgrade' | sed 's/^/  migrations applied: /' ) || fatal "migrations"

# M083's watermark is a prerequisite of an evaluation context, and M084 consumes
# it rather than creating it.
sudo -u postgres psql -q -d "$DB" -c \
  "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES ('WM-WALK')" \
  >/dev/null 2>&1

# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

write_configuration() {  # $1 = path, $2 = leverage, $3 = kill switch
  cat > "$1" <<JSON
{
  "configuration_governance_id": "CFG-WALK", "configuration_version": ${4:-1},
  "base_currency": "USD", "permitted_markets": ["XNAS"],
  "watchlist": ["AAPL", "MSFT"], "prohibited_instruments": ["PENNY"],
  "maximum_deployable_capital": "10000", "maximum_capital_per_trade": "2000",
  "maximum_percent_per_trade": "20", "minimum_cash_reserve": "1000",
  "maximum_simultaneous_positions": 3, "maximum_daily_loss": "500",
  "maximum_daily_order_count": 10, "minimum_price": "5", "maximum_price": "1000",
  "minimum_liquidity_shares": 100000, "maximum_spread_percent": "1",
  "maximum_estimated_slippage_percent": "1", "maximum_evidence_age_seconds": 86400,
  "maximum_market_data_age_seconds": 60, "permitted_session": "REGULAR",
  "earliest_entry_time": "10:00:00", "latest_entry_time": "15:30:00",
  "mandatory_liquidation_time": "15:45:00", "operator_timezone": "Europe/Helsinki",
  "exchange_calendar_policy": "XNAS-REGULAR-2026", "proposal_expiry_seconds": 300,
  "approval_expiry_seconds": 120, "default_order_type": "LIMIT",
  "permitted_order_types": ["LIMIT", "MARKET"], "limit_price_policy": "ASK",
  "stop_loss_percent": "2", "profit_exit_percent": "4",
  "maximum_leverage": "$2", "short_selling_permitted": false,
  "overnight_positions_permitted": false, "account_mode": "PREPARATION",
  "kill_switch": "$3"
}
JSON
}

write_inputs() {  # $1 = path, $2 = ask, $3 = feed kind, $4 = adv, $5 = symbol
  cat > "$1" <<JSON
{
  "quote": {
    "quote_id": "QTE-WALK", "provider_id": "OPERATOR-ASSERTED", "symbol": "${5:-AAPL}",
    "bid": "$(echo "$2 - 0.15" | bc)", "ask": "$2", "last_trade": "$2",
    "observed_at": "$OBSERVED", "feed_kind": "$3"
  },
  "account": {
    "account_snapshot_id": "ACC-WALK", "provider_id": "OPERATOR-ASSERTED",
    "account_reference": "PREP-1", "base_currency": "USD",
    "cash_available": "5000", "equity_total": "10000",
    "realized_pnl_today": "0", "orders_submitted_today": 0,
    "observed_at": "$OBSERVED"
  },
  "session": {
    "session_id": "SES-WALK", "provider_id": "OPERATOR-ASSERTED",
    "market": "XNAS", "status": "OPEN", "observed_at": "$OBSERVED"
  },
  "instrument": {
    "symbol": "${5:-AAPL}", "market": "XNAS", "currency": "USD",
    "is_fractionable": false, "lot_size": 1
  },
  "liquidity": {
    "symbol": "${5:-AAPL}", "average_daily_volume_shares": $4, "observed_at": "$OBSERVED"
  },
  "cost_estimate": {
    "estimate_id": "CST-WALK", "provider_id": "OPERATOR-ASSERTED", "symbol": "${5:-AAPL}",
    "commission": "1.00", "estimated_slippage_percent": "0.1",
    "observed_at": "$OBSERVED"
  },
  "positions": [], "open_orders": [], "evidence_age_seconds": "60"
}
JSON
}

write_configuration "$WORK/configuration.json" "1" "DISENGAGED"
write_configuration "$WORK/leveraged.json"     "2" "DISENGAGED"
write_inputs "$WORK/inputs.json"        "200.10" "REAL_TIME" 50000000
write_inputs "$WORK/inputs-delayed.json" "200.10" "DELAYED"  50000000
write_inputs "$WORK/inputs-illiquid.json" "200.10" "REAL_TIME" 1000
# Every snapshot must describe the symbol being evaluated -- the engine refuses
# a mismatched set outright, which the first draft of this script tripped over
# by asking about TSLA while handing it AAPL's quote. So the off-watchlist
# demonstration needs a genuinely TSLA-shaped input set.
write_inputs "$WORK/inputs-tsla.json" "200.10" "REAL_TIME" 50000000 "TSLA"

cat > "$WORK/context.json" <<JSON
{
  "evaluation_context_id": "ECX-WALK", "configuration_governance_id": "CFG-WALK",
  "configuration_version": 1, "watermark_governance_id": "WM-WALK",
  "quote_id": "QTE-WALK", "account_snapshot_id": "ACC-WALK",
  "session_id": "SES-WALK", "cost_estimate_id": "CST-WALK",
  "instrument_universe_version": "UNIVERSE-2026-06", "strategy_version": "STRATEGY-0001",
  "created_at": "$AT"
}
JSON

# ---------------------------------------------------------------------------
# The operator's own path, in the order a human walks it.
# ---------------------------------------------------------------------------

step "validate a policy file, touching no database"
run 0 "${BIN}-validate-trading-configuration" "$WORK/configuration.json"

step "a leveraged policy is refused before it can be stored"
run 1 "${BIN}-validate-trading-configuration" "$WORK/leveraged.json"

step "store the policy as version 1"
run 0 "${BIN}-save-trading-configuration" "$WORK/configuration.json"

step "read the stored policy back"
run 0 "${BIN}-show-trading-configuration" CFG-WALK 1

step "open an evaluation context, binding it to the M083 watermark"
run 0 "${BIN}-open-evaluation-context" "$WORK/context.json"

step "evaluate one instrument"
run 0 "${BIN}-prepare-trade-proposal" PRP-WALK ECX-WALK AAPL "$AT" "$WORK/inputs.json"

step "read the proposal and its derived terms"
run 0 "${BIN}-get-trade-proposal" PRP-WALK

step "the queue awaiting a human decision"
run 0 "${BIN}-list-trade-proposals" PREPARED

step "the system reports what it is and what it cannot do"
run 0 "${BIN}-system-status"

step "a human approves -- the one command no automation may run"
run 0 "${BIN}-decide-trade-proposal" PRP-WALK DEC-WALK APPROVE operator-1 "$AT"

step "derive the single never-submitted intent the approval permits"
run 0 "${BIN}-issue-order-intent" INT-WALK PRP-WALK IDEM-WALK "$AT"

step "read the intent back -- NOT_SUBMITTED, and nothing can change that"
run 0 "${BIN}-get-order-intent" INT-WALK

step "a second intent for the same proposal is refused"
run 1 "${BIN}-issue-order-intent" INT-WALK-2 PRP-WALK IDEM-WALK-2 "$AT"

step "the whole chain behind the proposal, for an auditor"
run 0 "${BIN}-audit-history" PRP-WALK

step "the global stop, and its effect on the next evaluation"
run 0 "${BIN}-kill-switch" status CFG-WALK

# ---------------------------------------------------------------------------
# NO_TRADE demonstrations. Three different refusals, each from a different
# rule, each shown with every check rather than only the reported reason.
# ---------------------------------------------------------------------------

step "NO_TRADE 1 of 3 — a feed that is not real time"
run 0 "${BIN}-explain-no-trade" ECX-WALK AAPL "$AT" "$WORK/inputs-delayed.json"

step "NO_TRADE 2 of 3 — liquidity below the configured floor"
run 0 "${BIN}-explain-no-trade" ECX-WALK AAPL "$AT" "$WORK/inputs-illiquid.json"

step "NO_TRADE 3 of 3 — an instrument that is not on the watchlist"
run 0 "${BIN}-explain-no-trade" ECX-WALK TSLA "$AT" "$WORK/inputs-tsla.json"

echo
echo "===================================================================="
echo " Steps run: $STEP.  Steps off their expected exit code: $FAILED."
echo "===================================================================="
exit $(( FAILED > 0 ))
