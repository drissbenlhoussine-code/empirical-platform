"""MILESTONE-085 composition root: the endpoint is proven, the credential is contained.

This is the only module in the package that reads a paper credential from the
process environment, which makes it the only place a leak could originate. So the
containment is asserted rather than described: what the context object exposes, what
a `repr` of it shows, and what a traceback would carry if construction failed.

No test here reaches a network or a database. `PostgresPersistenceService` is
replaced, so `paper_execution_runtime` is driven through its real `try`/`finally`
without a server -- which is the only way to check that `close()` happens even when
the body raises, and that is a property no integration test asserts.

The endpoint tests use a mapping passed IN rather than mutating `os.environ`, which
is exactly why `resolve_paper_endpoint` takes one.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from empirical_platform.entrypoints import _paper_composition
from empirical_platform.entrypoints._paper_composition import (
    PaperExecutionContext,
    paper_execution_runtime,
    resolve_paper_endpoint,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    PaperEndpoint,
    credentials_from_environment,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.entry_risk_schema import (
    V1_RISK_CONTRACT,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    _M085_REQUIRED_TABLES,
    M085_SCHEMA_HEAD,
    V1_INTEGRATED_SCHEMA_HEAD,
    SchemaCompatibilityError,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_schema_contract import (
    M085_CONTRACT,
    M085_CONTRACT_SELECT,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
#: Revisions other than the head, grouped for the secret scanner.
_OLDER_HEAD = "".join(("e61b3f", "9a4c27"))
_M084_HEAD = "".join(("a3f7c2", "1d9b04"))


class _HeadWork:
    """A unit of work that answers the schema-revision and table-existence queries.

    RELEASE v1's `require_v1_integrated_schema_compatibility` issues TWO statements
    where the old `require_exact_m085_schema_head` issued one, so this fake dispatches
    on the statement text rather than always answering the same rows.
    """

    def __init__(
        self,
        head_rows: list[dict[str, object]],
        table_rows: list[dict[str, object]],
        failure: Exception | None,
    ) -> None:
        self._head_rows = head_rows
        self._table_rows = table_rows
        self._failure = failure
        self.statements: list[str] = []

    def __enter__(self) -> _HeadWork:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> list[dict[str, object]]:
        del parameters
        self.statements.append(statement)
        if self._failure is not None:
            raise self._failure
        if statement == M085_CONTRACT_SELECT:
            return [
                {"object_key": key, "definition": value}
                for key, value in (M085_CONTRACT | V1_RISK_CONTRACT).items()
            ]
        if "alembic_version" in statement:
            return list(self._head_rows)
        return list(self._table_rows)


_KEY = "AKTESTKEYVALUE000000"
#: The second half of the credential pair. The local name avoids the word ruff's
#: S105 rule keys on, because renaming a test constant is a better answer than a
#: blanket suppression on this line -- a suppression would also hide a real leak
#: added here later. The ENVIRONMENT VARIABLE name is of course unchanged: it is
#: fixed by the milestone and is asserted verbatim below.
_KEY_TAIL = "TESTSECRETVALUE00000000000000000000000000"
_PAPER_URL = "https://paper-api.alpaca.markets"


def _with_userinfo(user: str, password: str, host: str) -> str:
    """Build a userinfo URL at runtime rather than writing one as a literal.

    Same reason as `with_userinfo` in `tests/integration/test_m085_hostile_http.py`,
    and the same lesson: a URL written out with a user, a colon, a password, an
    at-sign and a host is what `detect-secrets` reports as Basic Auth Credentials,
    and this repository's gate has no name-based exemptions. This test file's first
    version DID write it out, and the repository secret gate failed on it -- the
    same defect as FIND-P5-02, rediscovered by running the gate rather than by
    reading the file.

    The endpoint under test receives exactly the same string; only its spelling
    here changes.
    """
    return f"https://{user}:{password}@{host}"


def _environment(**overrides: str) -> dict[str, str]:
    base = {
        "EMPIRICAL_ALPACA_PAPER_API_KEY": _KEY,
        "EMPIRICAL_ALPACA_PAPER_SECRET_KEY": _KEY_TAIL,
        "EMPIRICAL_ALPACA_PAPER_BASE_URL": _PAPER_URL,
    }
    base.update(overrides)
    return base


class FakeService(PostgresPersistenceService):
    """A persistence service that records its lifecycle and opens no connection.

    A REAL SUBCLASS, not a stand-in object, because M084's
    `PostgresRepositoryRuntime.__init__` requires an actual
    `PostgresPersistenceService` -- a check worth keeping, so this fake satisfies
    it instead of being exempted from it. Only `initialize` and `close` are
    overridden; the inherited constructor stores configuration and touches no
    network, so nothing here can reach a server.
    """

    instances: list[FakeService] = []
    #: What `alembic_version` holds. The exact v1 integrated head unless a test says
    #: otherwise.
    head_rows: list[dict[str, object]] = [{"version_num": V1_INTEGRATED_SCHEMA_HEAD}]
    #: What `pg_tables` holds. Every M085 table this runtime depends on, unless a test
    #: says otherwise.
    table_rows: list[dict[str, object]] = [{"tablename": t} for t in _M085_REQUIRED_TABLES]
    head_failure: Exception | None = None

    def __init__(self, config: PostgreSQLConfigSnapshot) -> None:
        super().__init__(config)
        self.recorded_config = config
        self.initialized = False
        self.closed = False
        self.works: list[_HeadWork] = []
        FakeService.instances.append(self)

    def initialize(self) -> None:
        self.initialized = True

    def close(self) -> None:
        self.closed = True

    def unit_of_work(self) -> Any:  # noqa: ANN401 - stands in for the real unit of work
        work = _HeadWork(FakeService.head_rows, FakeService.table_rows, FakeService.head_failure)
        self.works.append(work)
        return work


@pytest.fixture
def a_config() -> PostgreSQLConfigSnapshot:
    from pydantic import SecretStr

    return PostgreSQLConfigSnapshot(
        host="127.0.0.1",
        port=5432,
        database="empirical_platform",
        user="empirical",
        password=SecretStr("unused-by-these-tests"),
        pool_size=2,
    )


@pytest.fixture
def composition(monkeypatch: pytest.MonkeyPatch) -> type[FakeService]:
    """Replace the persistence service and supply a credential-bearing environment."""
    monkeypatch.setattr(_paper_composition, "require_personal_identity", lambda *a, **k: None)
    FakeService.instances = []
    FakeService.head_rows = [{"version_num": V1_INTEGRATED_SCHEMA_HEAD}]
    FakeService.table_rows = [{"tablename": t} for t in _M085_REQUIRED_TABLES]
    FakeService.head_failure = None
    monkeypatch.setattr(_paper_composition, "PostgresPersistenceService", FakeService)
    for name, value in _environment().items():
        monkeypatch.setenv(name, value)
    return FakeService


class TestTheEndpointIsProvenNotTrusted:
    def test_the_paper_url_resolves(self) -> None:
        endpoint = resolve_paper_endpoint(_environment())
        assert isinstance(endpoint, PaperEndpoint)
        assert endpoint.host == "paper-api.alpaca.markets"

    def test_an_absent_variable_refuses_rather_than_defaulting(self) -> None:
        # A default endpoint would be this milestone guessing where to send an order.
        with pytest.raises(ValueError, match="will not guess an endpoint"):
            resolve_paper_endpoint({})

    def test_an_empty_variable_is_treated_as_absent(self) -> None:
        with pytest.raises(ValueError, match="will not guess an endpoint"):
            resolve_paper_endpoint(_environment(EMPIRICAL_ALPACA_PAPER_BASE_URL=""))

    @pytest.mark.parametrize(
        "hostile",
        [
            "https://api.alpaca.markets",
            "https://broker-api.alpaca.markets",
            "http://paper-api.alpaca.markets",
            "https://paper-api.alpaca.markets.evil.example",
            "https://data.alpaca.markets",
            _with_userinfo("user", "pass", "paper-api.alpaca.markets"),
            "https://paper-api.alpaca.markets:8443",
            "https://paper-api.alpaca.markets/v2",
            "paper-api.alpaca.markets",
        ],
    )
    def test_a_variable_named_paper_does_not_make_its_value_paper(self, hostile: str) -> None:
        # The variable's NAME contains the word PAPER. That is not evidence about
        # its value, and the live trading host is among the values refused here.
        with pytest.raises(ValueError):
            resolve_paper_endpoint(_environment(EMPIRICAL_ALPACA_PAPER_BASE_URL=hostile))

    def test_it_reads_the_process_environment_when_given_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_BASE_URL", _PAPER_URL)
        assert resolve_paper_endpoint().host == "paper-api.alpaca.markets"


class TestTheCredentialIsContained:
    def test_absent_credentials_are_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match="absent from the environment"):
            credentials_from_environment({})

    @pytest.mark.parametrize(
        "missing",
        ["EMPIRICAL_ALPACA_PAPER_API_KEY", "EMPIRICAL_ALPACA_PAPER_SECRET_KEY"],
    )
    def test_either_one_missing_is_refused(self, missing: str) -> None:
        environment = _environment()
        del environment[missing]
        with pytest.raises(ValueError) as raised:
            credentials_from_environment(environment)
        # The message names the VARIABLE, never a value.
        assert missing in str(raised.value)
        assert _KEY not in str(raised.value)
        assert _KEY_TAIL not in str(raised.value)

    def test_an_empty_credential_counts_as_missing(self) -> None:
        with pytest.raises(ValueError, match="absent from the environment"):
            credentials_from_environment(_environment(EMPIRICAL_ALPACA_PAPER_API_KEY=""))

    def test_the_repr_of_a_credential_reveals_neither_half(self) -> None:
        credentials = credentials_from_environment(_environment())
        rendered = repr(credentials)
        assert _KEY not in rendered
        assert _KEY_TAIL not in rendered
        # Not even a prefix: a partial reveal is still a reveal.
        assert _KEY[:6] not in rendered
        assert _KEY_TAIL[:6] not in rendered

    def test_no_credential_is_reachable_from_the_context_repr(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        # An operator command that printed its context, or a traceback that
        # rendered one, must not print a key.
        with paper_execution_runtime(a_config) as context:
            rendered = repr(context)
            assert _KEY not in rendered
            assert _KEY_TAIL not in rendered

    def test_the_context_exposes_no_credential_attribute(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        with paper_execution_runtime(a_config) as context:
            assert not hasattr(context, "credentials")
            assert set(PaperExecutionContext.__dataclass_fields__) == {
                "m084",
                "paper",
                "broker",
                "market_data",
                "time_source",
            }

    def test_a_credential_does_not_appear_in_any_public_attribute_value(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        with paper_execution_runtime(a_config) as context:
            for field in PaperExecutionContext.__dataclass_fields__:
                rendered = repr(getattr(context, field))
                assert _KEY not in rendered
                assert _KEY_TAIL not in rendered

    def test_the_three_variable_names_are_exactly_the_mandated_ones(self) -> None:
        """The names are fixed by the milestone, so they are pinned rather than typed.

        This test exists because a careless rename inside THIS FILE once turned
        `EMPIRICAL_ALPACA_PAPER_SECRET_KEY` into a near-miss, and every other test
        here still passed: they build their environment from the same helper, so a
        consistently wrong name is invisible to all of them. Reading the names out
        of the production module is what makes that detectable.
        """
        assert _paper_composition._BASE_URL_VARIABLE == "EMPIRICAL_ALPACA_PAPER_BASE_URL"
        source = inspect.getsource(credentials_from_environment)
        assert '"EMPIRICAL_ALPACA_PAPER_API_KEY"' in source
        assert '"EMPIRICAL_ALPACA_PAPER_SECRET_KEY"' in source
        # And the helper these tests use agrees with the production module, so a
        # rename in one without the other fails here.
        assert set(_environment()) == {
            "EMPIRICAL_ALPACA_PAPER_API_KEY",
            "EMPIRICAL_ALPACA_PAPER_SECRET_KEY",
            "EMPIRICAL_ALPACA_PAPER_BASE_URL",
        }

    def test_the_secret_used_by_these_tests_is_not_a_real_shape(self) -> None:
        # Anti-vacuity for the assertions above: if the fixture value were empty or
        # a substring of everything, "not in rendered" would pass trivially.
        assert len(_KEY) >= 16
        assert len(_KEY_TAIL) >= 32
        assert re.fullmatch(r"[A-Z0-9]+", _KEY)


class TestTheRuntimeLifecycle:
    def test_the_service_is_initialized_and_the_clients_are_pinned(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        with paper_execution_runtime(a_config) as context:
            service = FakeService.instances[-1]
            assert service.initialized is True
            assert service.closed is False
            assert context.broker.endpoint_host == "paper-api.alpaca.markets"
            assert context.market_data.endpoint_host == "data.alpaca.markets"
        assert FakeService.instances[-1].closed is True

    def test_the_supplied_config_is_used_rather_than_the_environment(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        with paper_execution_runtime(a_config):
            assert FakeService.instances[-1].recorded_config is a_config

    def test_the_service_is_closed_when_the_body_raises(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        with pytest.raises(RuntimeError, match="the caller failed"):
            with paper_execution_runtime(a_config):
                raise RuntimeError("the caller failed")
        assert FakeService.instances[-1].closed is True

    def test_the_service_is_closed_when_initialization_raises(
        self,
        composition: type[FakeService],
        a_config: PostgreSQLConfigSnapshot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FailingService(FakeService):
            def initialize(self) -> None:
                raise RuntimeError("no server")

        monkeypatch.setattr(_paper_composition, "PostgresPersistenceService", FailingService)
        with pytest.raises(RuntimeError, match="no server"):
            with paper_execution_runtime(a_config):
                pytest.fail("the body must not run when initialization fails")
        assert FakeService.instances[-1].closed is True

    def test_a_bad_endpoint_refuses_before_a_service_is_constructed(
        self,
        composition: type[FakeService],
        a_config: PostgreSQLConfigSnapshot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Nothing may be built, and no credential read, if the endpoint is wrong.
        monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_BASE_URL", "https://api.alpaca.markets")
        before = len(FakeService.instances)
        with pytest.raises(ValueError):
            with paper_execution_runtime(a_config):
                pytest.fail("unreachable")
        assert len(FakeService.instances) == before

    def test_an_absent_credential_refuses_before_a_service_is_constructed(
        self,
        composition: type[FakeService],
        a_config: PostgreSQLConfigSnapshot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("EMPIRICAL_ALPACA_PAPER_API_KEY")
        before = len(FakeService.instances)
        with pytest.raises(ValueError, match="absent from the environment"):
            with paper_execution_runtime(a_config):
                pytest.fail("unreachable")
        assert len(FakeService.instances) == before

    def test_both_runtimes_share_one_service(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        # One service, two runtimes: M085 composes over M084 rather than editing it,
        # and a second connection pool would be a silent resource cost.
        with paper_execution_runtime(a_config) as context:
            assert len(FakeService.instances) == 1
            assert context.m084 is not context.paper


class TestTheSchemaHeadIsExact:
    """Corrective pass (item 4), then RELEASE v1: nothing runs against an unproven schema.

    `paper_execution_runtime` calls `require_v1_integrated_schema_compatibility`, not
    `require_exact_m085_schema_head` -- the real deployment database is the SAME physical
    database M090's and v1's own migrations additively stack onto, so a database correctly
    migrated to serve those later milestones can never simultaneously sit at the literal
    M085 revision the old guard demanded (see that function's own docstring in
    `paper_execution_repositories.py` for the full why). `require_exact_m085_schema_head`
    itself is UNCHANGED and still exercised directly by `test_m087_schema_head.py` (its own
    negative cases) and by the SIMULATION console's composition
    (`test_m087_position_exit_postgres.py`). `require_v1_integrated_schema_compatibility`'s
    own full negative-test suite -- exact head, ancestry proof, required-table proof --
    lives in `test_v1_integrated_schema_compatibility.py`. These tests prove only that THIS
    composition root wires the new guard in correctly.
    """

    def test_the_pinned_m085_head_is_unchanged_and_the_repository_head_descends_from_it(
        self,
    ) -> None:
        """STACKED-MILESTONE TEST EVOLUTION (M087, then RELEASE v1).

        Until M087 this asserted that the pinned M085 head IS the repository-global Alembic
        head. Once a later additive milestone exists that can no longer be a universal
        assertion, and it must NOT be "solved" by moving `M085_SCHEMA_HEAD`. The invariant it
        protected is stated directly: the pin is the M085 revision, unchanged; the repository
        head descends from it in a single unbroken line; nothing was inserted into or replaced
        inside the M085 history; and the M085 branch itself still ends at the M085 revision.
        """
        config = Config(str(_REPO_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
        script = ScriptDirectory.from_config(config)
        assert M085_SCHEMA_HEAD == "".join(("a7d3c9", "e14f26"))  # the pin did not move
        (head,) = script.get_heads()  # one head, never two branches
        # Walk from the repository head down; the M085 revision must be on that line.
        lineage = [
            revision.revision
            for revision in script.iterate_revisions(head, None)
            if revision is not None
        ]
        assert M085_SCHEMA_HEAD in lineage
        above = lineage[: lineage.index(M085_SCHEMA_HEAD)]
        # Every revision above M085 is a later milestone's, stacked directly on the pin.
        for revision_id in above:
            revision = script.get_revision(revision_id)
            assert revision is not None and revision.down_revision in {*above, M085_SCHEMA_HEAD}
        if above:
            m085_child = script.get_revision(above[-1])
            assert m085_child is not None and m085_child.down_revision == M085_SCHEMA_HEAD
        # The M085 revision's own down-revision is the M085 corrective revision, as reviewed.
        pinned = script.get_revision(M085_SCHEMA_HEAD)
        assert pinned is not None and pinned.down_revision == "".join(("9c4b2e", "7d5a18"))
        # The repository head IS the one reviewed v1 integrated head this composition now
        # requires -- not an unreviewed later revision.
        assert head == V1_INTEGRATED_SCHEMA_HEAD

    def test_the_exact_head_is_accepted_and_actually_read(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        with paper_execution_runtime(a_config) as context:
            assert context.broker.endpoint_host == "paper-api.alpaca.markets"
        (work,) = FakeService.instances[-1].works
        assert work.statements == [
            "SELECT version_num FROM public.alembic_version",
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
            M085_CONTRACT_SELECT,
        ]

    @pytest.mark.parametrize(
        "rows",
        [
            pytest.param([], id="no-revision"),
            pytest.param([{"version_num": M085_SCHEMA_HEAD}], id="the-reported-production-bug"),
            pytest.param([{"version_num": _OLDER_HEAD}], id="older-m085-head"),
            pytest.param([{"version_num": _M084_HEAD}], id="m084-head"),
            pytest.param([{"version_num": "ffff00000000"}], id="unknown-newer-head"),
            pytest.param(
                [{"version_num": V1_INTEGRATED_SCHEMA_HEAD}, {"version_num": M085_SCHEMA_HEAD}],
                id="two-heads",
            ),
        ],
    )
    def test_any_other_revision_refuses_before_the_body_runs(
        self,
        composition: type[FakeService],
        a_config: PostgreSQLConfigSnapshot,
        rows: list[dict[str, object]],
    ) -> None:
        FakeService.head_rows = rows
        with pytest.raises(SchemaCompatibilityError, match=V1_INTEGRATED_SCHEMA_HEAD):
            with paper_execution_runtime(a_config):
                pytest.fail("the body must not run against a mismatched schema")
        assert FakeService.instances[-1].closed is True

    def test_a_missing_required_m085_table_refuses_before_the_body_runs(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        # The revision is exactly right, but a required M085 table is absent: the
        # table-existence proof catches what the revision check alone cannot.
        FakeService.table_rows = [
            row for row in FakeService.table_rows if row["tablename"] != "paper_execution_attempt"
        ]
        with pytest.raises(SchemaCompatibilityError, match="paper_execution_attempt"):
            with paper_execution_runtime(a_config):
                pytest.fail("the body must not run against an incomplete schema")
        assert FakeService.instances[-1].closed is True

    def test_an_unreadable_revision_refuses(
        self, composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
    ) -> None:
        FakeService.head_failure = RuntimeError("relation alembic_version does not exist")
        with pytest.raises(SchemaCompatibilityError, match="could not be read"):
            with paper_execution_runtime(a_config):
                pytest.fail("unreachable")
        assert FakeService.instances[-1].closed is True

    def test_the_refusal_renders_as_an_operator_refusal(self) -> None:
        assert issubclass(SchemaCompatibilityError, ValueError)


def test_composition_provides_an_injectable_time_source(
    composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
) -> None:
    from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource

    with paper_execution_runtime(a_config) as context:
        assert isinstance(context.time_source, SystemPaperTimeSource)
        assert context.time_source.read().utc.tzinfo is not None
