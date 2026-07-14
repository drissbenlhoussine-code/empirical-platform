import json

import pytest
from pytest import CaptureFixture

from empirical_platform.entrypoints.health import health_payload
from empirical_platform.entrypoints.health import main as health_main
from empirical_platform.entrypoints.version import main as version_main
from empirical_platform.entrypoints.version import version_payload
from empirical_platform.shared.config.settings import load_settings


def test_health_payload_contains_static_foundation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_ENVIRONMENT", "test")
    load_settings.cache_clear()

    try:
        assert health_payload() == {"environment": "test", "status": "ok"}
    finally:
        load_settings.cache_clear()


def test_health_main_prints_json(
    capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMPIRICAL_PLATFORM_ENVIRONMENT", "test")
    load_settings.cache_clear()

    try:
        health_main()
    finally:
        load_settings.cache_clear()

    assert json.loads(capsys.readouterr().out) == {"environment": "test", "status": "ok"}


def test_version_payload_contains_package_version() -> None:
    assert version_payload() == {"version": "0.0.0"}


def test_version_main_prints_json(capsys: CaptureFixture[str]) -> None:
    version_main()
    assert json.loads(capsys.readouterr().out) == {"version": "0.0.0"}
