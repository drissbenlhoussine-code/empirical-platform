"""MILESTONE-084 negative fixture: a FIX engine in application code.

FIX connectivity is named separately from the broker SDKs because it is the
other route by which an order could reach a venue.
"""

import quickfix

__all__ = ["quickfix"]
