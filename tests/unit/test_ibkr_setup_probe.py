import json

import pytest
from empirical_ibkr.session import IBKRSession
from tests.unit.test_ibkr_sdk_boundary import session as session

from empirical_platform.entrypoints.ibkr_owner_setup import main


def test_setup_probe_is_read_only_and_does_not_claim_database_acceptance(
    session: IBKRSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--account", "DU12345", "--symbol", "NOKIA"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "READ_ONLY_CONNECTION_VERIFIED"
    assert result["broker_writes"] == 0
    assert result["database_guards"] == "NOT_CHECKED_BY_CONNECTIVITY_PROBE"
    assert session._client.submitted == []


def test_setup_failure_reports_no_server_payload_or_credentials(
    session: IBKRSession,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(self: IBKRSession) -> None:
        raise RuntimeError("private server payload")

    monkeypatch.setattr(IBKRSession, "connect", fail)
    assert main(["--account", "DU12345", "--symbol", "NOKIA"]) == 2
    message = capsys.readouterr().out
    assert "private" not in message and "DU12345" not in message
    assert json.loads(message)["broker_writes"] == 0
