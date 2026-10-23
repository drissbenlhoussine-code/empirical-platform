"""Versioned immutable entry risk evidence; legacy absence never means unlimited risk."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any


def money(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("risk money must be a finite Decimal")
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def validate_limits(quantity: object, loss: object) -> None:
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("maximum position quantity must be a positive integer")
    if not isinstance(loss, Decimal) or not loss.is_finite() or loss <= 0:
        raise ValueError("maximum planned loss must be a positive finite Decimal")


@dataclass(frozen=True, slots=True)
class EntryRiskContract:
    """The approved ceiling/stop/quantity and independent caps, never a dispatch-time stop."""

    entry_ceiling: Decimal
    stop_price: Decimal
    quantity: int
    maximum_position_quantity_shares: int
    maximum_planned_loss_per_trade: Decimal
    planned_loss: Decimal

    def __post_init__(self) -> None:
        validate_limits(self.maximum_position_quantity_shares, self.maximum_planned_loss_per_trade)
        for value in (self.entry_ceiling, self.stop_price, self.planned_loss):
            money(value)
        if self.stop_price <= 0 or self.entry_ceiling <= self.stop_price:
            raise ValueError("approved stop must be positive and below entry ceiling")
        if (
            type(self.quantity) is not int
            or not 0 < self.quantity <= self.maximum_position_quantity_shares
        ):
            raise ValueError("approved quantity exceeds governed share cap")
        evaluated = planned_loss(self.entry_ceiling, self.stop_price, self.quantity)
        if (
            self.planned_loss != evaluated
            or not 0 <= evaluated <= self.maximum_planned_loss_per_trade
        ):
            raise ValueError("planned loss differs from approved terms or exceeds governed cap")

    def document(self) -> dict[str, Any]:
        return {
            "version": 2,
            "entry_ceiling": money(self.entry_ceiling),
            "stop_price": money(self.stop_price),
            "quantity": self.quantity,
            "maximum_position_quantity_shares": self.maximum_position_quantity_shares,
            "maximum_planned_loss_per_trade": money(self.maximum_planned_loss_per_trade),
            "planned_loss": money(self.planned_loss),
        }

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.document(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def read_risk(value: object) -> EntryRiskContract | None:
    if value is None:
        return None  # explicitly historical; current v1 send requires version 2
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value.get("version") != 2
    ):
        raise ValueError("invalid entry risk contract version")
    for name in ("entry_ceiling", "stop_price", "maximum_planned_loss_per_trade", "planned_loss"):
        if not isinstance(value.get(name), str):
            raise ValueError("risk money must be an exact decimal string")
    return EntryRiskContract(
        entry_ceiling=Decimal(value["entry_ceiling"]),
        stop_price=Decimal(value["stop_price"]),
        quantity=value["quantity"],
        maximum_position_quantity_shares=value["maximum_position_quantity_shares"],
        maximum_planned_loss_per_trade=Decimal(value["maximum_planned_loss_per_trade"]),
        planned_loss=Decimal(value["planned_loss"]),
    )


def planned_loss(entry: Decimal, stop: Decimal, quantity: int) -> Decimal:
    """Exact subtraction/multiplication, independent of ambient Decimal precision."""
    money(entry)
    money(stop)
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("risk quantity must be a positive whole number")
    with localcontext() as context:
        context.prec = (
            max(len(entry.as_tuple().digits), len(stop.as_tuple().digits))
            + abs(int(entry.as_tuple().exponent) - int(stop.as_tuple().exponent))
            + len(str(quantity))
            + 4
        )
        return (entry - stop) * quantity
