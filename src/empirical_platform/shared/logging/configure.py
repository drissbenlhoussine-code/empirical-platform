"""Structured logging configuration."""

from __future__ import annotations

import logging

import structlog

from empirical_platform.shared.config.settings import LoggingSettings


def configure_logging(settings: LoggingSettings) -> None:
    """Configure deterministic structured logging."""
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        cache_logger_on_first_use=True,
    )
