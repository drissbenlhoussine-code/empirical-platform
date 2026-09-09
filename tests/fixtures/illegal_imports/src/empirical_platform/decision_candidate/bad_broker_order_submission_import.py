"""MILESTONE-084 negative fixture: a broker order client in domain code.

Never imported at runtime. It exists so that the architecture checker is
proven to reject an order-submission dependency rather than merely being
believed to.
"""

import alpaca

__all__ = ["alpaca"]
