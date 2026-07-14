import importlib

from empirical_platform import __version__


def test_version_available() -> None:
    assert __version__ == "0.0.0"


def test_packages_import() -> None:
    modules = [
        "empirical_platform.acquisition",
        "empirical_platform.archive",
        "empirical_platform.audit",
        "empirical_platform.campaign",
        "empirical_platform.datasets",
        "empirical_platform.decision_candidate",
        "empirical_platform.evidence",
        "empirical_platform.governance",
        "empirical_platform.identifiers",
        "empirical_platform.normalization",
        "empirical_platform.registry",
        "empirical_platform.review",
        "empirical_platform.validation",
    ]

    for module in modules:
        assert importlib.import_module(module) is not None
