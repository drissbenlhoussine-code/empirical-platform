"""Daily research session: one-command orchestration of the frozen
M057-M061/M069 research stack into one immutable, persisted, auditable
session.

MILESTONE-070. This module owns only the pure value objects and the
one genuinely M070-specific piece of logic: `derive_observation_window`,
the as-of temporal firewall that decides which already-acquired bars a
session may see. Every other capability a session composes (market-data
acquisition, candidate evaluation, ranking, risk gating, position
sizing, historical backtesting) is the unmodified, frozen output of
M057-M061/M069 -- this module never recomputes any of it. The actual
sequencing/orchestration of those handlers lives in the usecase layer
(`usecases/run_daily_research_session.py`), since it is inherently
side-effecting glue, not a pure domain computation.

A session is persisted exactly once, at the end of one in-process
orchestration run (mirroring the established M057-M069 "compute once,
persist immutably" pattern rather than Campaign/Run's own heavier
optimistic-concurrency lifecycle machinery -- a daily session runs
start-to-finish within a single CLI invocation; nothing needs to observe
it mid-flight). `ResearchSessionStatus` still carries the full
CREATED/ACQUIRING_DATA/RUNNING_RESEARCH/COMPLETED/FAILED vocabulary the
orchestrator genuinely moves through in-process (and emits as
structured log events) -- only COMPLETED/FAILED are ever a session's own
terminal persisted value, which is honest: the enum documents the real
state machine, the persisted row captures its real outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from empirical_platform.decision_candidate.historical_backtest import HistoricalInstrumentSeries
from empirical_platform.decision_candidate.market_data import Bar, ObservationWindow
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId

#: Persisted verbatim on every session (mirrors the M066/M068 claim
#: -honesty precedent): research output is never a trading instruction,
#: historical evidence is never a future-performance guarantee, and no
#: broker order is ever submitted anywhere in this codebase.
RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS: tuple[str, ...] = (
    "Research output is not a trading instruction.",
    "Historical evidence does not predict future performance.",
    "Backtest results are not expected profit.",
    "The data source may have limitations (delisted symbols, corporate-action "
    "gaps, vendor outages, unofficial-endpoint instability).",
    "No broker order was submitted.",
)


class ResearchSessionStatus(StrEnum):
    """Closed session-level status vocabulary. Only `COMPLETED`/`FAILED`
    are ever a session's own terminal persisted value; the earlier
    states describe the in-process orchestration sequence honestly even
    though nothing external observes a session mid-flight."""

    CREATED = "CREATED"
    ACQUIRING_DATA = "ACQUIRING_DATA"
    RUNNING_RESEARCH = "RUNNING_RESEARCH"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StageStatus(StrEnum):
    """Closed per-stage status vocabulary. `SKIPPED` covers a stage that
    was never attempted because an earlier stage already failed --
    distinct from `FAILED`, so the manifest never implies a stage ran
    when it did not (mission Phase 8: "do not hide partial failures")."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StageName(StrEnum):
    """Closed, ordered stage vocabulary. Every stage below composes an
    already-frozen milestone's own handler; none reimplements its
    business logic (mission Phase 3)."""

    GOVERNANCE_SETUP = "GOVERNANCE_SETUP"
    DATA_ACQUISITION = "DATA_ACQUISITION"
    DATASET_INTEGRITY_CHECK = "DATASET_INTEGRITY_CHECK"
    CANDIDATE_SCAN = "CANDIDATE_SCAN"
    TRADE_PLANNING = "TRADE_PLANNING"
    POSITION_SIZING = "POSITION_SIZING"
    BACKTEST_EVIDENCE = "BACKTEST_EVIDENCE"


@dataclass(frozen=True, slots=True)
class StageRecord:
    """One immutable record of a single stage's own attempt: when it
    started/finished, its own outcome, the authority it consumed, the
    identity it produced, and -- when it failed -- inspectable error
    metadata (mission Phase 9: "underlying exception semantics should
    remain inspectable")."""

    stage_name: StageName
    stage_version: str | None
    started_at: datetime
    completed_at: datetime | None
    status: StageStatus
    input_authority: str
    output_identity: str | None
    error_type: str | None
    error_message: str | None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if not self.input_authority.strip():
            raise ValueError("input_authority must be non-empty")
        if self.status is StageStatus.FAILED:
            if self.error_type is None or not self.error_type.strip():
                raise ValueError("a FAILED stage must carry a non-empty error_type")
            if self.error_message is None or not self.error_message.strip():
                raise ValueError("a FAILED stage must carry a non-empty error_message")
            if self.completed_at is None:
                raise ValueError("a FAILED stage must carry completed_at")
        elif self.status in (StageStatus.PENDING, StageStatus.SKIPPED):
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("a PENDING/SKIPPED stage must carry no error metadata")
        elif self.status is StageStatus.COMPLETED:
            if self.completed_at is None:
                raise ValueError("a COMPLETED stage must carry completed_at")
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("a COMPLETED stage must carry no error metadata")


@dataclass(frozen=True, slots=True)
class ResearchDecisionEntry:
    """One immutable, per-instrument summary of what the session decided
    -- referencing the frozen M057/M059/M060 authorities by governance
    id, never duplicating their own content (mission Phase 14: "prefer
    references to frozen authorities")."""

    rank: int | None
    instrument_symbol: str
    decision_candidate_governance_id: str
    scan_decision: str
    trade_plan_governance_id: str | None
    trade_plan_decision: str | None
    position_plan_governance_id: str | None

    def __post_init__(self) -> None:
        if not self.instrument_symbol.strip():
            raise ValueError("instrument_symbol must be non-empty")
        if not self.decision_candidate_governance_id.strip():
            raise ValueError("decision_candidate_governance_id must be non-empty")
        if not self.scan_decision.strip():
            raise ValueError("scan_decision must be non-empty")
        if self.rank is not None and self.rank < 1:
            raise ValueError("rank must be at least 1 when set")


@dataclass(frozen=True, slots=True)
class ResearchSession:
    """One immutable, persisted daily research session: the full audit
    trail of one `run-daily-research` invocation, from real-market-data
    acquisition through candidate generation, risk gating, sizing, and
    historical backtest evidence."""

    identity: DomainIdentity[ResearchSessionId]
    created_at: datetime
    as_of: datetime
    requested_universe: tuple[str, ...]
    data_source: str

    dataset_id: str | None
    dataset_version: str | None
    dataset_sha256: str | None

    strategy_id: str | None
    strategy_version: str | None
    ranking_model_id: str | None
    ranking_model_version: str | None
    risk_policy_id: str | None
    risk_policy_version: str | None
    sizing_policy_id: str | None
    sizing_policy_version: str | None

    campaign_governance_id: str
    run_governance_id: str
    evidence_package_governance_id: str
    scan_governance_id: str | None

    status: ResearchSessionStatus
    failed_stage: StageName | None
    failure_type: str | None
    failure_message: str | None
    completed_at: datetime | None

    stage_manifest: tuple[StageRecord, ...]
    decisions: tuple[ResearchDecisionEntry, ...]

    candidate_count: int
    accepted_trade_plan_count: int
    rejected_trade_plan_count: int
    position_plan_count: int

    backtest_run_governance_id: str | None
    backtest_evaluated_opportunity_count: int | None
    backtest_executed_trade_count: int | None

    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[ResearchSessionId]")
        if not isinstance(self.identity.governance_id, ResearchSessionId):
            raise TypeError("identity governance_id must be a ResearchSessionId")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        if not self.requested_universe:
            raise ValueError("requested_universe must contain at least 1 instrument")
        if len(set(self.requested_universe)) != len(self.requested_universe):
            raise ValueError("requested_universe must not contain duplicate instruments")
        if not self.data_source.strip():
            raise ValueError("data_source must be non-empty")
        for field_name in (
            "campaign_governance_id",
            "run_governance_id",
            "evidence_package_governance_id",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if not self.stage_manifest:
            raise ValueError("stage_manifest must contain at least 1 stage")
        for earlier, later in zip(self.stage_manifest, self.stage_manifest[1:], strict=False):
            if later.started_at < earlier.started_at:
                raise ValueError("stage_manifest must be ordered by non-decreasing started_at")
        if tuple(self.limitations) != RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS:
            raise ValueError(
                "limitations must be exactly RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS"
            )
        if self.candidate_count < 0:
            raise ValueError("candidate_count must be non-negative")
        if self.accepted_trade_plan_count < 0 or self.rejected_trade_plan_count < 0:
            raise ValueError("trade plan counts must be non-negative")
        if self.position_plan_count < 0:
            raise ValueError("position_plan_count must be non-negative")
        if self.position_plan_count > self.accepted_trade_plan_count:
            raise ValueError("position_plan_count must not exceed accepted_trade_plan_count")

        if self.status is ResearchSessionStatus.COMPLETED:
            if self.failed_stage is not None or self.failure_type is not None:
                raise ValueError("a COMPLETED session must carry no failure metadata")
            if self.failure_message is not None:
                raise ValueError("a COMPLETED session must carry no failure_message")
            if self.completed_at is None:
                raise ValueError("a COMPLETED session must carry completed_at")
            if any(s.status is StageStatus.FAILED for s in self.stage_manifest):
                raise ValueError("a COMPLETED session must have no FAILED stage in its manifest")
        elif self.status is ResearchSessionStatus.FAILED:
            if self.failed_stage is None:
                raise ValueError("a FAILED session must carry failed_stage")
            if self.failure_type is None or not self.failure_type.strip():
                raise ValueError("a FAILED session must carry a non-empty failure_type")
            if self.failure_message is None or not self.failure_message.strip():
                raise ValueError("a FAILED session must carry a non-empty failure_message")
            if not any(s.status is StageStatus.FAILED for s in self.stage_manifest):
                raise ValueError(
                    "a FAILED session's own stage_manifest must record which stage failed"
                )
        else:
            raise ValueError(
                "a persisted ResearchSession's own terminal status must be COMPLETED or FAILED"
            )

    @property
    def is_completed(self) -> bool:
        return self.status is ResearchSessionStatus.COMPLETED

    @property
    def ranked_decisions(self) -> tuple[ResearchDecisionEntry, ...]:
        """Ranked (rank is not None) decisions only, ascending by rank."""
        ranked = [d for d in self.decisions if d.rank is not None]
        ranked.sort(key=lambda d: d.rank if d.rank is not None else 0)
        return tuple(ranked)


def derive_shared_evaluation_timestamp(
    series_by_instrument: dict[str, HistoricalInstrumentSeries],
    *,
    as_of: datetime,
) -> datetime | None:
    """The M070 as-of temporal firewall's own first step: find the most
    recent bar timestamp every requested instrument shares, restricted
    to timestamps at or before `as_of` (mission Phase 7 -- a session for
    historical as-of T must never consume data after T). A scan universe
    requires every instrument to share exactly one evaluation cutoff
    (see `scan.validate_scan_universe`) -- this is the one, coordinated
    cutoff every instrument's own `ObservationWindow` is built against,
    never each instrument independently choosing its own last-available
    bar (which could silently desynchronize the universe on any single
    -instrument data gap). Returns `None` when no such shared timestamp
    exists."""
    if not series_by_instrument:
        return None
    timestamp_sets = [
        {bar.timestamp for bar in series.bars if bar.timestamp <= as_of}
        for series in series_by_instrument.values()
    ]
    shared = set.intersection(*timestamp_sets) if timestamp_sets else set()
    return max(shared) if shared else None


def derive_observation_window(
    series: HistoricalInstrumentSeries,
    *,
    evaluation_timestamp: datetime,
    reference_window_size: int,
) -> ObservationWindow | None:
    """Build one instrument's own `ObservationWindow` ending exactly at
    `evaluation_timestamp` (the shared cutoff from
    `derive_shared_evaluation_timestamp`) -- never a bar after it
    (mission Phase 7's own temporal firewall, enforced a second time at
    the single-instrument level). Returns `None` when the exact
    evaluation bar is missing or fewer than `reference_window_size`
    bars strictly precede it -- never pads, forward-fills, or silently
    shrinks the window."""
    eligible: tuple[Bar, ...] = tuple(
        bar for bar in series.bars if bar.timestamp <= evaluation_timestamp
    )
    if not eligible or eligible[-1].timestamp != evaluation_timestamp:
        return None
    required = reference_window_size + 1
    if len(eligible) < required:
        return None
    return ObservationWindow(bars=eligible[-required:])
