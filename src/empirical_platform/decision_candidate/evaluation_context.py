"""MILESTONE-084 -- the Evaluation Context: what a decision actually consumed.

WHAT THIS IS. One persisted record binding a stable context identity to the
exact identities and versions of the material inputs that were loaded and used
while constructing a proposal.

THE M083 WATERMARK IS CONSUMED, NOT ATTACHED. `build_evaluation_context`
requires the caller to pass a watermark that was actually loaded from the
database, and it reads that watermark's own stored receipt set to derive both
`consumed_receipt_count` and `consumed_receipt_digest`. Neither is supplied by
the caller, and neither can be supplied by the caller. A context therefore
cannot be constructed for a watermark nobody read, and a later reader can
recompute the digest from the persisted watermark to check that the context
names the set it claims -- see `recompute_consumed_receipt_digest`.

NO POST-HOC BINDING. A context is created before and for one specific
evaluation. There is deliberately no function anywhere in this milestone that
attaches a context to an already-completed historical decision: doing so would
manufacture the appearance that a past decision consumed evidence it never saw,
which is precisely the post-hoc association MILESTONE-083's own authority
refuses to support.

WHAT A CONTEXT PROVES.
  - which persisted input identities were bound to this evaluation;
  - which configuration version governed it;
  - that the recorded evidence set matches the watermark it names;
  - that the binding was created by the sanctioned path.

WHAT IT DOES NOT PROVE.
  - that the M082 receipt payloads behind the watermark were historically true;
  - any commit time, market chronology or wall-clock ordering;
  - that the resulting proposal was profitable, fillable or broker-acceptable;
  - that evidence which is absent never existed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)

__all__ = [
    "EvaluationContext",
    "build_evaluation_context",
    "recompute_consumed_receipt_digest",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64
_DIGEST_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")

#: Domain separator. Without it, a digest over receipt identities could collide
#: with an equally-shaped digest computed elsewhere for a different purpose.
_DIGEST_PREFIX = "empirical-platform/m084/consumed-receipt-set/v1"


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def recompute_consumed_receipt_digest(watermark: EvaluationEvidenceWatermark) -> str:
    """Digest the watermark's stored receipt-identity set, in its stored order.

    M083 guarantees that order is canonical (ascending, ``COLLATE "C"``), so the
    digest is stable for a given set. It is a binding check, not a proof that
    the receipts behind those identities describe anything true.
    """
    if not isinstance(watermark, EvaluationEvidenceWatermark):
        raise ValueError("watermark must be a loaded EvaluationEvidenceWatermark")
    payload = "\n".join(
        (_DIGEST_PREFIX, watermark.watermark_governance_id, *watermark.receipt_governance_ids)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """The immutable set of input identities one evaluation actually consumed."""

    evaluation_context_id: str
    configuration_governance_id: str
    configuration_version: int

    #: The M083 watermark this evaluation consumed. Required: an evaluation with
    #: no evidence binding is not an evaluation this milestone will represent.
    watermark_governance_id: str
    consumed_receipt_count: int
    consumed_receipt_digest: str

    #: Provider observation identities, each required so that a later reader can
    #: name exactly which snapshot the decision saw.
    quote_id: str
    account_snapshot_id: str
    session_id: str
    cost_estimate_id: str | None

    #: Optional upstream research identities, present when the evaluation was
    #: driven from a persisted research session or decision candidate.
    research_session_id: str | None
    decision_candidate_id: str | None

    instrument_universe_version: str
    strategy_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "evaluation_context_id",
            "configuration_governance_id",
            "watermark_governance_id",
            "quote_id",
            "account_snapshot_id",
            "session_id",
            "instrument_universe_version",
            "strategy_version",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        for field_name in ("cost_estimate_id", "research_session_id", "decision_candidate_id"):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field=field_name)

        if isinstance(self.configuration_version, bool) or not isinstance(
            self.configuration_version, int
        ):
            raise ValueError("configuration_version must be an int")
        if self.configuration_version < 1:
            raise ValueError("configuration_version must start at 1")

        if isinstance(self.consumed_receipt_count, bool) or not isinstance(
            self.consumed_receipt_count, int
        ):
            raise ValueError("consumed_receipt_count must be an int")
        if self.consumed_receipt_count < 0:
            raise ValueError("consumed_receipt_count must not be negative")

        if not isinstance(self.consumed_receipt_digest, str) or not _DIGEST_PATTERN.match(
            self.consumed_receipt_digest
        ):
            raise ValueError("consumed_receipt_digest must be 64 lowercase hexadecimal characters")

        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None:
            raise ValueError("created_at must be a timezone-aware datetime")


def build_evaluation_context(
    *,
    evaluation_context_id: str,
    configuration: OperatorTradingConfiguration,
    watermark: EvaluationEvidenceWatermark,
    quote_id: str,
    account_snapshot_id: str,
    session_id: str,
    cost_estimate_id: str | None,
    instrument_universe_version: str,
    strategy_version: str,
    created_at: datetime,
    research_session_id: str | None = None,
    decision_candidate_id: str | None = None,
) -> EvaluationContext:
    """Bind one evaluation to the exact inputs it consumed.

    `watermark` is a real, already-loaded `EvaluationEvidenceWatermark`. The
    receipt count below is read from that object's own stored set, which is why
    a caller cannot fabricate a context for evidence it never loaded, and cannot
    overstate how much evidence was behind the decision.
    """
    if not isinstance(watermark, EvaluationEvidenceWatermark):
        raise ValueError(
            "watermark must be a loaded EvaluationEvidenceWatermark: an evaluation "
            "context cannot be built from a watermark identity alone"
        )
    if not isinstance(configuration, OperatorTradingConfiguration):
        raise ValueError("configuration must be an OperatorTradingConfiguration")

    return EvaluationContext(
        evaluation_context_id=evaluation_context_id,
        configuration_governance_id=configuration.configuration_governance_id,
        configuration_version=configuration.configuration_version,
        watermark_governance_id=watermark.watermark_governance_id,
        # Both derived from the loaded watermark's own stored set -- never parameters.
        consumed_receipt_count=watermark.captured_receipt_count,
        consumed_receipt_digest=recompute_consumed_receipt_digest(watermark),
        quote_id=quote_id,
        account_snapshot_id=account_snapshot_id,
        session_id=session_id,
        cost_estimate_id=cost_estimate_id,
        research_session_id=research_session_id,
        decision_candidate_id=decision_candidate_id,
        instrument_universe_version=instrument_universe_version,
        strategy_version=strategy_version,
        created_at=created_at,
    )
