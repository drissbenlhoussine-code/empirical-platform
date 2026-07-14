import json
import logging

import structlog
from pytest import CaptureFixture

from empirical_platform.shared.config.settings import LoggingSettings
from empirical_platform.shared.logging.configure import configure_logging
from empirical_platform.shared.logging.context import LogContext


def test_log_context_as_dict() -> None:
    context = LogContext(correlation_id="corr-1", campaign_id="CAMP-0001")
    assert context.as_dict()["correlation_id"] == "corr-1"
    assert context.as_dict()["campaign_id"] == "CAMP-0001"


def test_structured_logging_outputs_json(capsys: CaptureFixture[str]) -> None:
    configure_logging(LoggingSettings(log_level="INFO"))
    logger = structlog.get_logger("test").bind(correlation_id="corr-1")
    logger.info("foundation_check")
    captured = capsys.readouterr()
    payload = json.loads(captured.err or captured.out)
    assert payload["event"] == "foundation_check"
    assert payload["correlation_id"] == "corr-1"
    logging.shutdown()
