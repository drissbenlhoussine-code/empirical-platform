"""Negative fixture: wrong method name (no `handle` method at all)."""

from __future__ import annotations

from empirical_platform.shared.contracts.query import QueryHandler


class Qry:
    pass


class Res:
    pass


class BadHandler:
    def process(self, query: Qry) -> Res:
        return Res()


handler: QueryHandler[Qry, Res] = BadHandler()
