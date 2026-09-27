"""MILESTONE-086 -- the deterministic SIMULATION broker behind the Operator Console.

WHAT THIS IS. A stand-in for the broker and market-data ports that MILESTONE-085's
handlers already require (`PaperBrokerPort`, `PaperMarketDataPort`). The handlers do not
know they are talking to a simulation: every identity rule, authorization rule, state
transition, reconciliation round and absence policy of M085 runs unchanged on top of it.
There is deliberately NO second execution state machine here -- this module answers
questions and records orders; M085 decides what those answers mean.

WHAT THIS IS NOT. It opens no socket, reads no credential and imports no HTTP client.
Nothing in it can reach Alpaca or any other venue. It is the ONLY broker the Operator
Console can construct in this milestone (see the composition root's capability
firewall), and its evidence is marked as simulated wherever a domain type leaves room
for a marker: broker order ids are `sim-...`, the account identifier is
`SIMULATION-ACCOUNT-...`, every payload carries `"simulation": true`, quotes come from
the `SIMULATION` source and the market-data host is `simulation.invalid` (a reserved,
unresolvable name). Two domain invariants leave no room and are stated plainly:
`PaperAccountSnapshot.endpoint_host` must equal the pinned paper host and
`PaperEnvironment` has only a PAPER member, so a simulated snapshot carries those two
values; the console never derives its SIMULATION badge from broker evidence but from the
capability the composition root selected.

DURABLE ON PURPOSE. A broker remembers the orders it received across the client's
restarts; a simulation that forgot them on restart would make every ambiguous dispatch
look like a never-delivered order and would resolve it REJECTED -- exactly the mistake
M085's reconciliation exists to avoid. The store is one JSON file, written atomically.
It is the simulator's own state, not an M085 table: no migration and no schema-head
change is involved.

SCENARIOS. Behaviour is chosen per symbol from a closed set, fixed when the simulation
day is loaded and recorded in the store, so a run is reproducible and a reviewer can
read which failure a symbol was staged to exercise.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    PaperOrderRequest,
)
from empirical_platform.decision_candidate.position_exit import PositionExitRequest
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerIdentityExistsError,
    BrokerIdentityUnresolvedError,
    BrokerNotSentError,
)

__all__ = [
    "SIMULATION_ACCOUNT_ID",
    "SimulationStateLock",
    "SimulationStateLockedError",
    "SIMULATION_MARKET_DATA_HOST",
    "SIMULATION_QUOTE_SOURCE",
    "SimulatedMarketData",
    "SimulatedOrder",
    "SimulatedPaperBroker",
    "SimulationExitScenario",
    "SimulationScenario",
    "SimulationStore",
    "default_exit_scenario_table",
    "default_scenario_table",
]

SIMULATION_ACCOUNT_ID = "SIMULATION-ACCOUNT-0001"
SIMULATION_MARKET_DATA_HOST = "simulation.invalid"
SIMULATION_QUOTE_SOURCE = "SIMULATION"

#: Alpaca's documented duplicate-identity code, echoed so M085's classifier recognises it.
_DUPLICATE_IDENTITY_CODE = 40010001
#: A documented definitive refusal (insufficient buying power).
_DEFINITIVE_REFUSAL_CODE = 40310000


class SimulationScenario(StrEnum):
    """What the simulated broker does with an order for a given symbol. Closed."""

    ACCEPTED_THEN_FILLED = "ACCEPTED_THEN_FILLED"
    ACCEPTED_NOT_FILLED = "ACCEPTED_NOT_FILLED"
    PARTIAL_FILL = "PARTIAL_FILL"
    BROKER_REJECTION = "BROKER_REJECTION"
    AMBIGUOUS_SUBMISSION = "AMBIGUOUS_SUBMISSION"
    NETWORK_FAILURE_BEFORE_SEND = "NETWORK_FAILURE_BEFORE_SEND"
    NETWORK_FAILURE_AFTER_POSSIBLE_SEND = "NETWORK_FAILURE_AFTER_POSSIBLE_SEND"
    CANCEL_SUCCESS = "CANCEL_SUCCESS"
    CANCEL_FILL_RACE = "CANCEL_FILL_RACE"
    RECONCILIATION_FINDS_ORDER = "RECONCILIATION_FINDS_ORDER"
    RECONCILIATION_NOT_FOUND = "RECONCILIATION_NOT_FOUND"
    RESTART_WHILE_UNKNOWN = "RESTART_WHILE_UNKNOWN"


#: Scenarios in which the request is DELIVERED but the answer is lost: the order exists
#: at the simulated broker and only reconciliation can find it.
_DELIVERED_BUT_AMBIGUOUS = frozenset(
    {
        SimulationScenario.AMBIGUOUS_SUBMISSION,
        SimulationScenario.NETWORK_FAILURE_AFTER_POSSIBLE_SEND,
        SimulationScenario.RECONCILIATION_FINDS_ORDER,
        SimulationScenario.RESTART_WHILE_UNKNOWN,
    }
)


class SimulationExitScenario(StrEnum):
    """What the simulated broker does with a MILESTONE-087 SELL-TO-CLOSE for a symbol. Closed.

    Chosen per symbol independently of the entry scenario, so a position opened by a filled
    entry can be closed under any exit behaviour a reviewer wants to see.
    """

    EXIT_FILLED = "EXIT_FILLED"
    EXIT_ACCEPTED_NOT_FILLED = "EXIT_ACCEPTED_NOT_FILLED"
    EXIT_PARTIAL_FILL = "EXIT_PARTIAL_FILL"
    EXIT_REJECTION = "EXIT_REJECTION"
    EXIT_FAILURE_BEFORE_SEND = "EXIT_FAILURE_BEFORE_SEND"
    EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND = "EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND"
    EXIT_RECONCILIATION_FINDS = "EXIT_RECONCILIATION_FINDS"
    EXIT_RECONCILIATION_NOT_FOUND = "EXIT_RECONCILIATION_NOT_FOUND"
    EXIT_CANCEL_FILL_RACE = "EXIT_CANCEL_FILL_RACE"
    EXIT_RESTART_WHILE_UNKNOWN = "EXIT_RESTART_WHILE_UNKNOWN"


_EXIT_DELIVERED_BUT_AMBIGUOUS = frozenset(
    {
        SimulationExitScenario.EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND,
        SimulationExitScenario.EXIT_RECONCILIATION_FINDS,
        SimulationExitScenario.EXIT_RESTART_WHILE_UNKNOWN,
    }
)

#: How an accepted order progresses on its second lookup, by scenario (entry and exit).
#: "fill": fills whole; "partial": fills half then rests; "rest": stays accepted;
#: "race": stays accepted, but a cancel request loses to a fill.
_PROGRESSION: dict[str, str] = {
    SimulationScenario.ACCEPTED_THEN_FILLED.value: "fill",
    SimulationScenario.ACCEPTED_NOT_FILLED.value: "rest",
    SimulationScenario.PARTIAL_FILL.value: "partial",
    SimulationScenario.BROKER_REJECTION.value: "fill",
    SimulationScenario.AMBIGUOUS_SUBMISSION.value: "fill",
    SimulationScenario.NETWORK_FAILURE_BEFORE_SEND.value: "fill",
    SimulationScenario.NETWORK_FAILURE_AFTER_POSSIBLE_SEND.value: "fill",
    SimulationScenario.CANCEL_SUCCESS.value: "rest",
    SimulationScenario.CANCEL_FILL_RACE.value: "race",
    SimulationScenario.RECONCILIATION_FINDS_ORDER.value: "fill",
    SimulationScenario.RECONCILIATION_NOT_FOUND.value: "fill",
    SimulationScenario.RESTART_WHILE_UNKNOWN.value: "fill",
    SimulationExitScenario.EXIT_FILLED.value: "fill",
    SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED.value: "rest",
    SimulationExitScenario.EXIT_PARTIAL_FILL.value: "partial",
    SimulationExitScenario.EXIT_REJECTION.value: "fill",
    SimulationExitScenario.EXIT_FAILURE_BEFORE_SEND.value: "fill",
    SimulationExitScenario.EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND.value: "fill",
    SimulationExitScenario.EXIT_RECONCILIATION_FINDS.value: "fill",
    SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND.value: "fill",
    SimulationExitScenario.EXIT_CANCEL_FILL_RACE.value: "race",
    SimulationExitScenario.EXIT_RESTART_WHILE_UNKNOWN.value: "fill",
}


def default_exit_scenario_table() -> dict[str, SimulationExitScenario]:
    """The staged exit behaviours. Symbols whose ENTRY fills (or is found filled) get one.

    AAPL closes cleanly; GOOGL fills half; JPM is refused; PG is accepted and rests; KO's
    answer is lost across a restart; JNJ's exit is lost and never found; V (after its entry
    is cancelled) fails before the send; MSFT (after its remainder is cancelled) races a
    cancel and fills; NVDA and AMZN never hold a position, so their behaviour is moot.
    """
    return {
        "AAPL": SimulationExitScenario.EXIT_FILLED,
        "MSFT": SimulationExitScenario.EXIT_CANCEL_FILL_RACE,
        "NVDA": SimulationExitScenario.EXIT_FILLED,
        "AMZN": SimulationExitScenario.EXIT_FILLED,
        "GOOGL": SimulationExitScenario.EXIT_PARTIAL_FILL,
        "META": SimulationExitScenario.EXIT_FILLED,
        "JPM": SimulationExitScenario.EXIT_REJECTION,
        "V": SimulationExitScenario.EXIT_FAILURE_BEFORE_SEND,
        "JNJ": SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND,
        "PG": SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED,
        "XOM": SimulationExitScenario.EXIT_RECONCILIATION_FINDS,
        "KO": SimulationExitScenario.EXIT_RESTART_WHILE_UNKNOWN,
    }


def default_scenario_table() -> dict[str, SimulationScenario]:
    """The staged day: one liquid US symbol per scenario a reviewer may want to see."""
    return {
        "AAPL": SimulationScenario.ACCEPTED_THEN_FILLED,
        "MSFT": SimulationScenario.PARTIAL_FILL,
        "NVDA": SimulationScenario.ACCEPTED_NOT_FILLED,
        "AMZN": SimulationScenario.BROKER_REJECTION,
        "GOOGL": SimulationScenario.AMBIGUOUS_SUBMISSION,
        "META": SimulationScenario.NETWORK_FAILURE_BEFORE_SEND,
        "JPM": SimulationScenario.NETWORK_FAILURE_AFTER_POSSIBLE_SEND,
        "V": SimulationScenario.CANCEL_SUCCESS,
        "JNJ": SimulationScenario.CANCEL_FILL_RACE,
        "PG": SimulationScenario.RECONCILIATION_FINDS_ORDER,
        "XOM": SimulationScenario.RECONCILIATION_NOT_FOUND,
        "KO": SimulationScenario.RESTART_WHILE_UNKNOWN,
    }


@dataclass(frozen=True, slots=True)
class SimulatedOrder:
    """One order the simulated broker RECEIVED, as it currently describes it."""

    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: str
    order_type: str
    limit_price: str | None
    time_in_force: str
    extended_hours: bool
    status: str
    filled_quantity: str
    filled_avg_price: str | None
    scenario: str
    lookups: int
    cancel_requested: bool
    received_at: str

    def view(self) -> SimulatedOrderView:
        return SimulatedOrderView(self)

    def payload(self) -> str:
        document: dict[str, Any] = {
            "id": self.broker_order_id,
            "client_order_id": self.client_order_id,
            "status": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.quantity,
            "type": self.order_type,
            "limit_price": self.limit_price,
            "time_in_force": self.time_in_force,
            "extended_hours": self.extended_hours,
            "filled_qty": self.filled_quantity,
            "filled_avg_price": self.filled_avg_price,
            "simulation": True,
            "scenario": self.scenario,
        }
        return json.dumps(document, sort_keys=True)


class SimulatedOrderView:
    """`BrokerOrderView` over a simulated order."""

    __slots__ = ("_order",)

    def __init__(self, order: SimulatedOrder) -> None:
        self._order = order

    @property
    def broker_order_id(self) -> str:
        return self._order.broker_order_id

    @property
    def client_order_id(self) -> str:
        return self._order.client_order_id

    @property
    def status(self) -> str:
        return self._order.status

    @property
    def symbol(self) -> str:
        return self._order.symbol

    @property
    def side(self) -> str:
        return self._order.side

    @property
    def quantity(self) -> str:
        return self._order.quantity

    @property
    def order_type(self) -> str:
        return self._order.order_type

    @property
    def limit_price(self) -> str | None:
        return self._order.limit_price

    @property
    def time_in_force(self) -> str | None:
        return self._order.time_in_force

    @property
    def extended_hours(self) -> bool | None:
        return self._order.extended_hours

    @property
    def filled_quantity(self) -> str:
        return self._order.filled_quantity

    @property
    def filled_avg_price(self) -> str | None:
        return self._order.filled_avg_price


@dataclass(frozen=True, slots=True)
class SimulatedClockView:
    is_open: bool
    timestamp: datetime
    next_open: datetime | None
    next_close: datetime | None


@dataclass(frozen=True, slots=True)
class SimulatedAssetView:
    symbol: str
    status: str = "active"
    tradable: bool = True
    asset_class: str = "us_equity"
    exchange: str = "SIMULATION"
    fractionable: bool = False


@dataclass(frozen=True, slots=True)
class SimulatedPositionView:
    symbol: str
    quantity: int


@dataclass(frozen=True, slots=True)
class SimulatedQuoteView:
    symbol: str
    bid: str | None
    ask: str | None
    captured_at: datetime
    source: str = SIMULATION_QUOTE_SOURCE


@dataclass
class _State:
    version: int = 1
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenarios: dict[str, str] = field(default_factory=dict)
    exit_scenarios: dict[str, str] = field(default_factory=dict)
    quotes: dict[str, dict[str, str]] = field(default_factory=dict)
    positions: dict[str, int] = field(default_factory=dict)
    cash: str = "100000"
    market_is_open: bool = True
    counter: int = 0


class SimulationStore:
    """The simulated broker's own durable memory: one JSON file, replaced atomically.

    Every mutation happens under one lock and is written before the method returns, so
    a process that dies right after `submit_order` answered still leaves the order
    where a restarted process will find it -- which is what a real broker does.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._state = self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> _State:
        if not self._path.exists():
            return _State()
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        state = _State()
        for name in ("orders", "scenarios", "exit_scenarios", "quotes", "positions"):
            value = raw.get(name)
            if isinstance(value, dict):
                setattr(state, name, value)
        if isinstance(raw.get("cash"), str):
            state.cash = raw["cash"]
        if isinstance(raw.get("market_is_open"), bool):
            state.market_is_open = raw["market_is_open"]
        if isinstance(raw.get("counter"), int):
            state.counter = raw["counter"]
        return state

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(self._state), indent=2, sort_keys=True)
        handle, temporary = tempfile.mkstemp(
            prefix=".simulation-", suffix=".json", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    # -- staging -----------------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._state = _State()
            self._save()

    def stage(
        self,
        *,
        scenarios: dict[str, SimulationScenario],
        quotes: dict[str, tuple[str, str]],
        cash: str = "100000",
        market_is_open: bool = True,
        exit_scenarios: dict[str, SimulationExitScenario] | None = None,
    ) -> None:
        """Fix the day's behaviour. Orders already received and positions held are kept."""
        with self._lock:
            self._state.scenarios = {
                symbol: scenario.value for symbol, scenario in scenarios.items()
            }
            if exit_scenarios is not None:
                self._state.exit_scenarios = {
                    symbol: scenario.value for symbol, scenario in exit_scenarios.items()
                }
            self._state.quotes = {
                symbol: {"bid": bid, "ask": ask} for symbol, (bid, ask) in quotes.items()
            }
            self._state.cash = cash
            self._state.market_is_open = market_is_open
            self._save()

    def set_market_open(self, is_open: bool) -> None:
        with self._lock:
            self._state.market_is_open = is_open
            self._save()

    # -- reads -------------------------------------------------------------------

    def scenario_for(self, symbol: str) -> SimulationScenario:
        with self._lock:
            raw = self._state.scenarios.get(symbol.upper())
        return SimulationScenario(raw) if raw else SimulationScenario.ACCEPTED_THEN_FILLED

    def scenarios(self) -> dict[str, SimulationScenario]:
        with self._lock:
            return {s: SimulationScenario(v) for s, v in self._state.scenarios.items()}

    def exit_scenario_for(self, symbol: str) -> SimulationExitScenario:
        with self._lock:
            raw = self._state.exit_scenarios.get(symbol.upper())
        return SimulationExitScenario(raw) if raw else SimulationExitScenario.EXIT_FILLED

    def exit_scenarios(self) -> dict[str, SimulationExitScenario]:
        with self._lock:
            return {s: SimulationExitScenario(v) for s, v in self._state.exit_scenarios.items()}

    def quote_for(self, symbol: str) -> tuple[str, str] | None:
        with self._lock:
            raw = self._state.quotes.get(symbol.upper())
        return None if raw is None else (raw["bid"], raw["ask"])

    def cash(self) -> str:
        with self._lock:
            return self._state.cash

    def market_is_open(self) -> bool:
        with self._lock:
            return self._state.market_is_open

    def position(self, symbol: str) -> int:
        with self._lock:
            return int(self._state.positions.get(symbol.upper(), 0))

    def order(self, client_order_id: str) -> SimulatedOrder | None:
        with self._lock:
            raw = self._state.orders.get(client_order_id)
        return None if raw is None else SimulatedOrder(**raw)

    def orders(self) -> tuple[SimulatedOrder, ...]:
        with self._lock:
            return tuple(SimulatedOrder(**raw) for raw in self._state.orders.values())

    def order_by_broker_id(self, broker_order_id: str) -> SimulatedOrder | None:
        for order in self.orders():
            if order.broker_order_id == broker_order_id:
                return order
        return None

    # -- writes ------------------------------------------------------------------

    def next_broker_order_id(self) -> str:
        with self._lock:
            self._state.counter += 1
            self._save()
            return f"sim-{self._state.counter:06d}"

    def put(self, order: SimulatedOrder) -> SimulatedOrder:
        with self._lock:
            self._state.orders[order.client_order_id] = asdict(order)
            self._save()
        return order

    def add_position(self, symbol: str, quantity: int) -> None:
        if quantity < 0:
            raise ValueError("add_position only adds; a sale goes through reduce_position")
        with self._lock:
            current = int(self._state.positions.get(symbol.upper(), 0))
            self._state.positions[symbol.upper()] = current + quantity
            self._save()

    def reduce_position(self, symbol: str, quantity: int) -> int:
        """Sell `quantity` shares out of the long held. The position can NEVER go below zero.

        Refuses -- and changes nothing -- when the sale would exceed the position. This is
        the simulator's own invariant (MILESTONE-087 rule 7), enforced under the same lock
        that reads the position, so two concurrent fills cannot cross zero together.
        """
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("a sale reduces the position by a positive whole quantity")
        with self._lock:
            current = int(self._state.positions.get(symbol.upper(), 0))
            if quantity > current:
                raise ValueError(
                    f"simulated position in {symbol.upper()} is {current}; a sale of {quantity} "
                    "would make it negative and is refused"
                )
            remaining = current - quantity
            if remaining == 0:
                self._state.positions.pop(symbol.upper(), None)
            else:
                self._state.positions[symbol.upper()] = remaining
            self._save()
            return remaining


def _now() -> datetime:
    return datetime.now(UTC)


class SimulationStateLockedError(RuntimeError):
    """Another Operator Console process already owns this simulation state directory."""


class SimulationStateLock:
    """One console per state directory, enforced by an operating-system file lock.

    The lock is taken BEFORE any database connection or store is opened and held for the
    process's whole life; a second process on the same directory is refused before it can
    read or mutate simulation state. Exclusive, non-blocking, released on `release()` or
    when the process dies (the OS drops it), so a crash never leaves a stale lock behind.
    Windows uses `msvcrt.locking`; POSIX uses `fcntl.flock`.
    """

    FILE_NAME = "console.lock"

    def __init__(self, state_dir: Path) -> None:
        self._path = Path(state_dir) / self.FILE_NAME
        self._handle: Any = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._path, "a+b")  # noqa: SIM115
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise SimulationStateLockedError(
                f"another Operator Console already owns the simulation state directory "
                f"{self._path.parent} (lock file {self._path.name}); refusing to start a second "
                "one. Stop it first, or use a different --state-dir."
            ) from error
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class SimulatedPaperBroker:
    """`PaperBrokerPort` over the simulation store. Deterministic; never on a network."""

    #: A domain invariant (`PaperAccountSnapshot.endpoint_host`) requires the pinned host.
    #: The console's SIMULATION badge does not come from this value; see the module docstring.
    endpoint_host = PAPER_ENDPOINT_HOST

    def __init__(self, store: SimulationStore, *, clock: Callable[[], datetime] = _now) -> None:
        self._store = store
        self._clock = clock

    @property
    def store(self) -> SimulationStore:
        return self._store

    # -- account, clock, assets --------------------------------------------------

    def fetch_account(self) -> tuple[int, dict[str, object]]:
        cash = self._store.cash()
        return 200, {
            "id": SIMULATION_ACCOUNT_ID,
            "status": "ACTIVE",
            "currency": "USD",
            "buying_power": cash,
            "cash": cash,
            "equity": cash,
            "multiplier": "1",
            "shorting_enabled": False,
            "trading_blocked": False,
            "transfers_blocked": False,
            "account_blocked": False,
            "trade_suspended_by_user": False,
            "simulation": True,
        }

    def fetch_clock(self) -> SimulatedClockView:
        now = self._clock()
        is_open = self._store.market_is_open()
        return SimulatedClockView(
            is_open=is_open,
            timestamp=now,
            next_open=None if is_open else now + timedelta(hours=12),
            next_close=now + timedelta(hours=4) if is_open else None,
        )

    def fetch_asset(self, symbol: str) -> SimulatedAssetView:
        return SimulatedAssetView(symbol=symbol.upper())

    def fetch_position(self, symbol: str) -> SimulatedPositionView | None:
        quantity = self._store.position(symbol)
        return (
            None
            if quantity == 0
            else SimulatedPositionView(symbol=symbol.upper(), quantity=quantity)
        )

    # -- orders ------------------------------------------------------------------

    def submit_order(
        self, order: PaperOrderRequest, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, SimulatedOrderView | None, str]:
        if before_send is not None:
            # As the real adapter does: whatever `before_send` raises means NOTHING was sent.
            try:
                before_send()
            except (BrokerNotSentError, BrokerIdentityExistsError, BrokerIdentityUnresolvedError):
                raise
            except Exception as error:  # noqa: BLE001 - mirrors the transport boundary
                raise BrokerNotSentError(
                    f"pre-send validation failed: {type(error).__name__}"
                ) from error

        scenario = self._store.scenario_for(order.symbol)
        if scenario is SimulationScenario.NETWORK_FAILURE_BEFORE_SEND:
            raise BrokerNotSentError(
                "simulated network failure before any byte of the request was sent"
            )

        existing = self._store.order(order.client_order_id)
        if existing is not None:
            # A faithful broker refuses a second order under an identity it already holds.
            raise BrokerIdentityExistsError(
                "simulated broker: an order already exists under this client_order_id",
                http_status=422,
                sanitized_body=json.dumps(
                    {
                        "code": _DUPLICATE_IDENTITY_CODE,
                        "message": "client_order_id must be unique",
                        "simulation": True,
                    }
                ),
                request_sent=True,
            )

        if scenario is SimulationScenario.BROKER_REJECTION:
            body = json.dumps(
                {
                    "code": _DEFINITIVE_REFUSAL_CODE,
                    "message": "simulated: insufficient buying power",
                    "simulation": True,
                }
            )
            return 403, None, body

        if scenario is SimulationScenario.RECONCILIATION_NOT_FOUND:
            # The request is LOST before the broker records anything, and the answer is
            # lost too. Reconciliation will never find it; the bounded policy decides.
            raise BrokerAmbiguousDispatchError(
                "simulated: the request timed out and the broker never received it"
            )

        received = self._store.put(
            SimulatedOrder(
                broker_order_id=self._store.next_broker_order_id(),
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side.lower(),
                quantity=str(order.quantity),
                order_type=order.order_type.value.lower(),
                limit_price=None if order.limit_price is None else str(order.limit_price),
                time_in_force=order.time_in_force.lower(),
                extended_hours=order.extended_hours,
                status="accepted",
                filled_quantity="0",
                filled_avg_price=None,
                scenario=scenario.value,
                lookups=0,
                cancel_requested=False,
                received_at=self._clock().isoformat(),
            )
        )
        if scenario in _DELIVERED_BUT_AMBIGUOUS:
            # Delivered, recorded, and the answer is lost on its way back.
            raise BrokerAmbiguousDispatchError(
                "simulated: the request was delivered but the answer was lost"
            )
        return 200, received.view(), received.payload()

    def submit_close_order(
        self, request: PositionExitRequest, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, SimulatedOrderView | None, str]:
        """MILESTONE-087: the one SELL-TO-CLOSE a human authorized, for an existing long only.

        Reduces an existing long position and nothing else: a request with no position, or
        for more than the position, is DEFINITIVELY refused (HTTP 403, the documented refusal
        code) before anything is recorded. The position moves only when the order fills, and
        `SimulationStore.reduce_position` refuses to cross zero. Every other behaviour
        (duplicate identity, not-sent, ambiguous, lost) mirrors `submit_order`.
        """
        if not isinstance(request, PositionExitRequest):
            raise TypeError("submit_close_order takes a PositionExitRequest")
        if before_send is not None:
            try:
                before_send()
            except (BrokerNotSentError, BrokerIdentityExistsError, BrokerIdentityUnresolvedError):
                raise
            except Exception as error:  # noqa: BLE001 - mirrors the transport boundary
                raise BrokerNotSentError(
                    f"pre-send validation failed: {type(error).__name__}"
                ) from error

        scenario = self._store.exit_scenario_for(request.symbol)
        if scenario is SimulationExitScenario.EXIT_FAILURE_BEFORE_SEND:
            raise BrokerNotSentError(
                "simulated network failure before any byte of the exit request was sent"
            )

        existing = self._store.order(request.client_order_id)
        if existing is not None:
            raise BrokerIdentityExistsError(
                "simulated broker: an order already exists under this client_order_id",
                http_status=422,
                sanitized_body=json.dumps(
                    {
                        "code": _DUPLICATE_IDENTITY_CODE,
                        "message": "client_order_id must be unique",
                        "simulation": True,
                    }
                ),
                request_sent=True,
            )

        held = self._store.position(request.symbol)
        if held <= 0:
            return (
                403,
                None,
                json.dumps(
                    {
                        "code": _DEFINITIVE_REFUSAL_CODE,
                        "message": "simulated: no long position to close",
                        "simulation": True,
                    }
                ),
            )
        if request.quantity > held:
            return (
                403,
                None,
                json.dumps(
                    {
                        "code": _DEFINITIVE_REFUSAL_CODE,
                        "message": (
                            f"simulated: insufficient qty ({held} held, "
                            f"{request.quantity} requested)"
                        ),
                        "simulation": True,
                    }
                ),
            )
        if scenario is SimulationExitScenario.EXIT_REJECTION:
            return (
                403,
                None,
                json.dumps(
                    {
                        "code": _DEFINITIVE_REFUSAL_CODE,
                        "message": "simulated: exit refused by the venue",
                        "simulation": True,
                    }
                ),
            )
        if scenario is SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND:
            raise BrokerAmbiguousDispatchError(
                "simulated: the exit request timed out and the broker never received it"
            )

        received = self._store.put(
            SimulatedOrder(
                broker_order_id=self._store.next_broker_order_id(),
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                side=request.broker_side,
                quantity=str(request.quantity),
                order_type=request.order_type.value.lower(),
                limit_price=None if request.limit_price is None else str(request.limit_price),
                time_in_force=request.time_in_force.lower(),
                extended_hours=request.extended_hours,
                status="accepted",
                filled_quantity="0",
                filled_avg_price=None,
                scenario=scenario.value,
                lookups=0,
                cancel_requested=False,
                received_at=self._clock().isoformat(),
            )
        )
        if scenario in _EXIT_DELIVERED_BUT_AMBIGUOUS:
            raise BrokerAmbiguousDispatchError(
                "simulated: the exit request was delivered but the answer was lost"
            )
        return 200, received.view(), received.payload()

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, SimulatedOrderView | None, str]:
        order = self._store.order(client_order_id)
        if order is None:
            return (
                404,
                None,
                json.dumps({"code": 40410000, "message": "order not found", "simulation": True}),
            )
        advanced = self._store.put(self._advance(order))
        return 200, advanced.view(), advanced.payload()

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]:
        order = self._store.order_by_broker_id(broker_order_id)
        if order is None:
            return 404, json.dumps(
                {"code": 40410000, "message": "order not found", "simulation": True}
            )
        if order.status in {"filled", "canceled", "rejected"}:
            return 422, json.dumps(
                {
                    "code": 42210000,
                    "message": f"simulated: order is already {order.status}",
                    "simulation": True,
                }
            )
        self._store.put(replace(order, cancel_requested=True, status="pending_cancel"))
        return 204, "{}"

    # -- progression -------------------------------------------------------------

    def _advance(self, order: SimulatedOrder) -> SimulatedOrder:
        """One lookup later, where does the simulated broker say this order stands?

        Deterministic in the number of lookups: the first lookup after acceptance still
        shows `accepted`, the second shows the scenario's outcome. Terminal statuses
        never change again.
        """
        lookups = order.lookups + 1
        behaviour = _PROGRESSION.get(order.scenario, "fill")
        if order.status in {"filled", "canceled", "rejected"}:
            return replace(order, lookups=lookups)
        if order.cancel_requested:
            if behaviour == "race":
                return self._filled(order, lookups)
            return replace(order, lookups=lookups, status="canceled")
        if lookups < 2:
            return replace(order, lookups=lookups, status="accepted")
        if behaviour == "partial":
            if order.status == "partially_filled":
                return replace(order, lookups=lookups)  # the rest keeps working
            quantity = int(order.quantity)
            part = quantity // 2
            if part < 1:
                return replace(order, lookups=lookups, status="accepted")
            # The filled part moves the position NOW: a buy adds it, a sell reduces it.
            self._move_position(order, part)
            return replace(
                order,
                lookups=lookups,
                status="partially_filled",
                filled_quantity=str(part),
                filled_avg_price=self._fill_price(order),
            )
        if behaviour in {"rest", "race"}:
            return replace(order, lookups=lookups, status="accepted")
        return self._filled(order, lookups)

    def _filled(self, order: SimulatedOrder, lookups: int) -> SimulatedOrder:
        if order.status != "filled":
            # Only the part not yet filled moves the position; a partial fill already did.
            remaining = int(order.quantity) - int(Decimal(order.filled_quantity))
            if remaining > 0:
                self._move_position(order, remaining)
        return replace(
            order,
            lookups=lookups,
            status="filled",
            filled_quantity=order.quantity,
            filled_avg_price=self._fill_price(order),
        )

    def _move_position(self, order: SimulatedOrder, quantity: int) -> None:
        """A buy adds to the long; a sell reduces it and can never cross zero."""
        if order.side == "sell":
            self._store.reduce_position(order.symbol, quantity)
        else:
            self._store.add_position(order.symbol, quantity)

    def _fill_price(self, order: SimulatedOrder) -> str:
        if order.limit_price is not None:
            return order.limit_price
        quote = self._store.quote_for(order.symbol)
        return quote[1] if quote is not None else "0"


class SimulatedMarketData:
    """`PaperMarketDataPort` over the staged quotes. Quotes only; it can place nothing."""

    endpoint_host = SIMULATION_MARKET_DATA_HOST

    def __init__(self, store: SimulationStore, *, clock: Callable[[], datetime] = _now) -> None:
        self._store = store
        self._clock = clock

    def fetch_quote(self, symbol: str) -> SimulatedQuoteView | None:
        quote = self._store.quote_for(symbol)
        if quote is None:
            return None
        bid, ask = quote
        # Two seconds old: fresh under any sane freshness limit, never zero-age.
        return SimulatedQuoteView(
            symbol=symbol.upper(),
            bid=bid,
            ask=ask,
            captured_at=self._clock() - timedelta(seconds=2),
        )


def decimal_text(value: Decimal | str) -> str:
    """Canonical decimal text for staged quotes (no exponent, no trailing zeros lost)."""
    return format(Decimal(value), "f")
