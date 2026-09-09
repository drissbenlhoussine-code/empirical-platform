"""MILESTONE-084 negative fixture: a broker order client in a usecase.

Uses the `from ... import` form so that both import shapes are covered.
"""

from ib_insync import IB

__all__ = ["IB"]
