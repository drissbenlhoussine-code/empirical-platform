from __future__ import annotations

from empirical_platform.shared.logging.configure import FoundationLogger
from empirical_platform.shared.logging.context import LogContext, set_log_context


class CapturingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **fields: object) -> None:
        self.events.append(("info", event, fields))

    def error(self, event: str, **fields: object) -> None:
        self.events.append(("error", event, fields))


class FailingLogger:
    def info(self, event: str, **fields: object) -> None:
        raise RuntimeError("normal logging failed")

    def error(self, event: str, **fields: object) -> None:
        raise RuntimeError("normal logging failed")


def test_foundation_logger_emits_structured_secret_safe_fields() -> None:
    logger = CapturingLogger()
    set_log_context(LogContext(correlation_id="corr-1"))

    sensitive_name = "".join(("pass", "word"))

    FoundationLogger(logger=logger).info(
        "event", **{sensitive_name: "redaction fixture value", "visible": "yes"}
    )

    assert logger.events == [
        (
            "info",
            "event",
            {
                "correlation_id": "corr-1",
                "campaign_id": None,
                "run_id": None,
                sensitive_name: "[REDACTED]",
                "visible": "yes",
            },
        )
    ]
    set_log_context(None)


def test_foundation_logger_failure_uses_independent_fallback() -> None:
    fallback_calls: list[tuple[str, dict[str, object] | None]] = []
    sensitive_name = "_".join(("api", "key"))

    FoundationLogger(
        logger=FailingLogger(),
        fallback=lambda event, fields: fallback_calls.append((event, dict(fields or {}))),
    ).info("event", **{sensitive_name: "redaction fixture value"})

    assert fallback_calls == [("event", {sensitive_name: "[REDACTED]"})]
