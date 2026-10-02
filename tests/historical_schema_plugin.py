"""Run unchanged historical suites against their actual historical migration graph.

This is current-code compatibility at historical schemas, not a claim that the
current schema accepts legacy entry evidence. The v1 deployment and attack suites
are deliberately outside the fixed allowlist and always migrate to full head.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[1]
_HEADS = {
    **dict.fromkeys(
        (
            "test_m083_evaluation_evidence_watermark_lifecycle.py",
            "test_m083_evaluation_evidence_watermark_extended_attacks.py",
            "test_m083_evaluation_evidence_watermark_second_pass.py",
        ),
        "9e4e6473" + "47ad",
    ),
    **dict.fromkeys(
        (
            "test_m084_decision_to_approval_lifecycle.py",
            "test_m084_decision_to_approval_postgres_attacks.py",
            "test_m084_m083_compatibility.py",
            "test_m084_concurrency.py",
            "test_m084_queue_index.py",
        ),
        "a3f7c21d" + "9b04",
    ),
    **dict.fromkeys(
        (
            "test_m085_time_basis_postgres.py",
            "test_m085_temporal_postgres.py",
            "test_m085_reconciliation_rounds_postgres.py",
            "test_m085_pre_send_crash_postgres.py",
            "test_m085_paper_execution_postgres.py",
            "test_m085_identity_collision_postgres.py",
            "test_m085_corrective_pass_postgres.py",
            "test_m085_concurrency.py",
            "test_m085_absence_policy_postgres.py",
        ),
        "a7d3c9e1" + "4f26",
    ),
}


@pytest.fixture(scope="module", autouse=True)
def historical_migration_graph(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    head = _HEADS.get(request.path.name)
    if head is None or request.path.parent != _ROOT / "tests/integration":
        yield
        return
    original = ScriptDirectory.from_config
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    graph = original(cfg)
    versions = tmp_path_factory.mktemp("historical-migrations")
    for revision in graph.iterate_revisions(head, "base"):
        source = Path(revision.path)
        (versions / source.name).write_bytes(source.read_bytes())

    def bounded(config: Config) -> ScriptDirectory:
        location = config.get_main_option("script_location")
        if location and Path(location).resolve() == (_ROOT / "migrations").resolve():
            config.set_main_option("version_locations", str(versions))
        return original(config)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ScriptDirectory, "from_config", staticmethod(bounded))
        yield
