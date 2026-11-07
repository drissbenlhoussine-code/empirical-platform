# ruff: noqa: ANN401
"""P2-2 -- a refused Prepare followed by another Prepare in the SAME second must never surface
a raw persistence/uniqueness error (the real Postgres context table is unique by id)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from tests.unit._m085_fakes import FakeAttempts, FakeMarketData, FakeTimeBases
from tests.unit._m086_fakes import MemoryContexts, MemoryWatermarks
from tests.unit.test_v1_paper_candidate_preparation import (
    _LiveQuote,
    _now,
    _open_broker,
    _repositories,
)

from empirical_platform.decision_candidate.evaluation_context import EvaluationContext
from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource
from empirical_platform.usecases.paper_operator_console import (
    V1PaperCandidateRefusedError,
    prepare_v1_paper_candidate,
)


@dataclass
class _HeldPosition:
    symbol: str = "AAPL"
    quantity: int = 1
    average_entry_price: str = "330.00"


class _StrictContexts(MemoryContexts):
    """Like the Postgres table: a second row with the same id is a uniqueness error."""

    def save(self, context: EvaluationContext) -> EvaluationContext:
        if context.evaluation_context_id in self.rows:
            raise RuntimeError(
                "duplicate key value violates unique constraint (evaluation_context)"
            )
        return super().save(context)


def _run(configurations: Any, contexts: Any, proposals: Any, *, broker: Any, now: datetime) -> Any:
    market_data = FakeMarketData(quote=_LiveQuote())
    return prepare_v1_paper_candidate(
        configurations=configurations,
        contexts=contexts,
        proposals=proposals,
        watermarks=MemoryWatermarks(),
        time_bases=FakeTimeBases(),
        broker=broker,
        market_data=market_data,
        bars=market_data,
        attempts=FakeAttempts(),
        time_source=SystemPaperTimeSource(),
        now=now,
    )


def test_a_refused_prepare_then_another_in_the_same_second_is_not_a_raw_error() -> None:
    configurations, _, proposals = _repositories()
    contexts = _StrictContexts()
    now = _now().replace(microsecond=0)

    # 1st click: the engine refuses (a position already exists) AFTER the context row is written.
    blocked = _open_broker()
    blocked.position = _HeldPosition()
    with pytest.raises(V1PaperCandidateRefusedError):
        _run(configurations, contexts, proposals, broker=blocked, now=now)
    assert len(contexts.rows) == 1  # the refused attempt really did persist its context

    # 2nd click, same second, nothing blocking any more: must succeed with a distinct id.
    prepared = _run(configurations, contexts, proposals, broker=_open_broker(), now=now)
    first_ids = {key for key in contexts.rows}
    assert len(first_ids) == 2
    assert prepared.proposal.proposal_governance_id.startswith("PRP-089-PAPER-")

    # 3rd click, same second again: still a distinct id, never a raw error.
    again = _run(configurations, contexts, proposals, broker=_open_broker(), now=now)
    ids = {
        prepared.proposal.proposal_governance_id,
        again.proposal.proposal_governance_id,
    }
    assert len(ids) == 2


def test_a_lost_same_id_race_is_a_clean_refusal_not_a_raw_error() -> None:
    configurations, _, proposals = _repositories()

    class _RacingContexts(_StrictContexts):
        def save(self, context: EvaluationContext) -> EvaluationContext:
            # a concurrent click wins the same id between our probe and our insert
            super().save(context)
            return super().save(context)

    contexts = _RacingContexts()
    with pytest.raises(V1PaperCandidateRefusedError, match="same moment"):
        _run(configurations, contexts, proposals, broker=_open_broker(), now=_now())
