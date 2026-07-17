"""Process-local domain primitives shared by future aggregate implementations."""

from empirical_platform.shared.domain.transitions import StateTransitionRecord
from empirical_platform.shared.domain.versioning import AggregateVersion, TransitionSequence

__all__ = [
    "AggregateVersion",
    "StateTransitionRecord",
    "TransitionSequence",
]
