"""Structured logging foundation."""

from empirical_platform.shared.logging.configure import configure_logging
from empirical_platform.shared.logging.context import LogContext

__all__ = ["LogContext", "configure_logging"]
