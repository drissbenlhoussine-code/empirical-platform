"""Positive fixture: a correctly-shaped handler, proving the mypy
subprocess invocation itself works."""

from __future__ import annotations

from empirical_platform.shared.contracts.query import QueryHandler


class Qry:
    pass


class Res:
    pass


class GoodHandler:
    def handle(self, query: Qry) -> Res:
        return Res()


handler: QueryHandler[Qry, Res] = GoodHandler()
