"""Negative fixture: no `handle` method at all."""

from __future__ import annotations

from empirical_platform.shared.contracts.query import QueryHandler


class Qry:
    pass


class Res:
    pass


class NoHandleAtAll:
    pass


handler: QueryHandler[Qry, Res] = NoHandleAtAll()
