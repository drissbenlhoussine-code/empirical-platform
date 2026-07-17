"""Versioning primitives for process-local domain objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class AggregateVersion:
    """Optimistic-concurrency version for one aggregate root."""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError("aggregate version must be an integer")
        if self.value < 0:
            raise ValueError("aggregate version must be non-negative")

    @classmethod
    def initial(cls) -> AggregateVersion:
        """Return the initial aggregate version."""
        return cls(0)

    def next(self) -> AggregateVersion:
        """Return the next aggregate version."""
        return AggregateVersion(self.value + 1)


@dataclass(frozen=True, slots=True, order=True)
class TransitionSequence:
    """Append-only transition ordering primitive inside one aggregate."""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError("transition sequence must be an integer")
        if self.value < 1:
            raise ValueError("transition sequence must be positive")

    @classmethod
    def initial(cls) -> TransitionSequence:
        """Return the first transition sequence."""
        return cls(1)

    def next(self) -> TransitionSequence:
        """Return the next transition sequence."""
        return TransitionSequence(self.value + 1)
