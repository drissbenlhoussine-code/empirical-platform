"""Negative fixture: `handle` returns an unrelated result type."""

from __future__ import annotations

from empirical_platform.shared.contracts.query import QueryHandler


class Qry:
    pass


class Res:
    pass


class OtherRes:
    pass


class WrongResultHandler:
    def handle(self, query: Qry) -> OtherRes:
        return OtherRes()


handler: QueryHandler[Qry, Res] = WrongResultHandler()
