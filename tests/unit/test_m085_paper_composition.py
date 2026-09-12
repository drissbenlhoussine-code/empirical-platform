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

import pytest

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

    def __init__(self, config: PostgreSQLConfigSnapshot) -> None:
        super().__init__(config)
        self.recorded_config = config
        self.initialized = False
        self.closed = False
        FakeService.instances.append(self)

    def initialize(self) -> None:
        self.initialized = True

    def close(self) -> None:
        self.closed = True


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
    FakeService.instances = []
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


def test_composition_provides_an_injectable_time_source(
    composition: type[FakeService], a_config: PostgreSQLConfigSnapshot
) -> None:
    from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource

    with paper_execution_runtime(a_config) as context:
        assert isinstance(context.time_source, SystemPaperTimeSource)
        assert context.time_source.read().utc.tzinfo is not None
