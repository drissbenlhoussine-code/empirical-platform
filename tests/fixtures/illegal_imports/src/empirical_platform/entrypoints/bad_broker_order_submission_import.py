"""MILESTONE-084 negative fixture: a broker order client in an entrypoint.

Uses a submodule path so that the rule is proven to match on the prefix and
not only on an exact top-level name.
"""

import alpaca.trading.client

__all__ = ["alpaca"]
