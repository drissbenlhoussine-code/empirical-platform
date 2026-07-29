"""Negative fixture: `handle` accepts an unrelated query type."""

from __future__ import annotations

from empirical_platform.shared.contracts.query import QueryHandler


class Qry:
    pass


class OtherQry:
    pass


class Res:
    pass


class TypedHandler:
    def handle(self, query: OtherQry) -> Res:
        return Res()


handler: QueryHandler[Qry, Res] = TypedHandler()
