"""REV-R2 -- boundary evidence is parsed strictly; ambiguous evidence is rejected as a whole.

`SEND_BOUNDARY_ENTERED` carries its binding as six canonical `key=value` tokens. The reviewed
parser overwrote duplicate keys with the last value and ignored malformed tokens, so ambiguous
or partly damaged evidence could still satisfy `send_boundary_event_binds`. The strict parser
accepts exactly the canonical record -- six tokens, in canonical order, each `key=value` with a
non-empty value free of whitespace and `=` -- and returns None for anything else: identical or
conflicting duplicates, empty values, malformed tokens, missing fields, unknown fields, truncated
or padded records. A None binding lends no lineage. Valid canonical records and legitimate
lost-acknowledgement recovery keep working (positive controls here and in
`test_m085_pre_send_crash.py`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from empirical_platform.decision_candidate.paper_execution import (
    SEND_BOUNDARY_BINDING_KEYS,
    SEND_BOUNDARY_EVENT_TYPE,
    PaperExecutionState,
    attempt_may_have_transmitted,
    parse_send_boundary_binding,
    send_boundary_binding,
    send_boundary_event_binds,
)

_FIELDS: dict[str, object] = {
    "attempt_id": "ATT-1",
    "authorization_id": "AUT-1",
    "request_fingerprint": "a" * 64,
    "account_reference": "ref:account",
    "client_order_id": "m085-0123456789abcdef",
    "identity_lookup_status": 404,
}
_CANONICAL = send_boundary_binding(**_FIELDS)  # type: ignore[arg-type]


def _attempt() -> SimpleNamespace:
    return SimpleNamespace(
        attempt_id="ATT-1",
        authorization_id="AUT-1",
        request_fingerprint="a" * 64,
        client_order_id="m085-0123456789abcdef",
        state=PaperExecutionState.SUBMISSION_IN_PROGRESS,
        failure_code=None,
    )


def _event(detail: object, *, attempt_id: str = "ATT-1") -> SimpleNamespace:
    return SimpleNamespace(
        event_type=SEND_BOUNDARY_EVENT_TYPE, attempt_id=attempt_id, detail=detail
    )


class TestTheCanonicalRecord:
    def test_the_producer_emits_exactly_the_canonical_keys_in_order(self) -> None:
        tokens = _CANONICAL.split(" ")
        assert [token.partition("=")[0] for token in tokens] == list(SEND_BOUNDARY_BINDING_KEYS)
        assert SEND_BOUNDARY_BINDING_KEYS == (
            "attempt",
            "authorization",
            "fingerprint",
            "account",
            "client_order_id",
            "identity_lookup",
        )

    def test_a_canonical_record_parses_and_binds(self) -> None:
        parsed = parse_send_boundary_binding(_CANONICAL)
        assert parsed == {
            "attempt": "ATT-1",
            "authorization": "AUT-1",
            "fingerprint": "a" * 64,
            "account": "ref:account",
            "client_order_id": "m085-0123456789abcdef",
            "identity_lookup": "404",
        }
        assert send_boundary_event_binds(
            _event(_CANONICAL), _attempt(), account_reference="ref:account"
        )
        assert attempt_may_have_transmitted(_attempt(), [_event(_CANONICAL)]) is True

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("attempt_id", ""),
            ("attempt_id", "ATT 1"),
            ("account_reference", "ref=account"),
            ("client_order_id", "m085-\t1"),
            ("authorization_id", " "),
        ],
    )
    def test_the_producer_refuses_values_that_could_not_be_parsed_back(
        self, field: str, value: str
    ) -> None:
        with pytest.raises(ValueError):
            send_boundary_binding(**{**_FIELDS, field: value})  # type: ignore[arg-type]


def _tampered(detail: str) -> list[tuple[str, str]]:
    tokens = detail.split(" ")
    return [
        ("identical duplicate appended", detail + " attempt=ATT-1"),
        ("conflicting duplicate appended", detail + " attempt=ATT-2"),
        (
            "conflicting duplicate in place of another field",
            " ".join(tokens[:2] + ["attempt=ATT-2"] + tokens[3:]),
        ),
        (
            "identical duplicate in place of another field",
            " ".join(tokens[:2] + ["attempt=ATT-1"] + tokens[3:]),
        ),
        ("empty value", detail.replace("authorization=AUT-1", "authorization=")),
        ("malformed token without =", detail.replace("account=ref:account", "account_ref:account")),
        (
            "malformed token with two =",
            detail.replace("account=ref:account", "account=ref=account"),
        ),
        ("missing field", " ".join(tokens[:-1])),
        ("truncated before the last value", detail[: -len("=404")]),
        ("truncated to the last key's equals sign", detail[: -len("404")]),
        ("unknown field appended", detail + " version=2"),
        (
            "unknown field replacing a required one",
            detail.replace("identity_lookup=404", "lookup=404"),
        ),
        ("fields out of canonical order", " ".join([tokens[1], tokens[0], *tokens[2:]])),
        ("double space separator", detail.replace(" fingerprint=", "  fingerprint=")),
        ("leading space", " " + detail),
        ("trailing space", detail + " "),
        ("key case changed", detail.replace("attempt=", "Attempt=")),
        (
            "value with embedded whitespace",
            detail.replace("account=ref:account", "account=ref:acc ount"),
        ),
        ("empty record", ""),
    ]


@pytest.mark.parametrize(
    ("label", "detail"),
    _tampered(_CANONICAL),
    ids=[label.replace(" ", "-").replace("'", "") for label, _ in _tampered(_CANONICAL)],
)
def test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole(label: str, detail: str) -> None:
    assert parse_send_boundary_binding(detail) is None, label
    assert (
        send_boundary_event_binds(_event(detail), _attempt(), account_reference="ref:account")
        is False
    ), label
    assert attempt_may_have_transmitted(_attempt(), [_event(detail)]) is False, label


def test_a_value_truncated_but_still_well_formed_is_refused_at_the_binding_step() -> None:
    truncated = _CANONICAL[: len(_CANONICAL) - 2]  # identity_lookup=4
    assert parse_send_boundary_binding(truncated) is not None, "well-formed text parses"
    assert (
        send_boundary_event_binds(_event(truncated), _attempt(), account_reference="ref:account")
        is False
    )
    assert attempt_may_have_transmitted(_attempt(), [_event(truncated)]) is False


@pytest.mark.parametrize("detail", [None, 42, b"bytes", ["attempt=ATT-1"], {"attempt": "ATT-1"}])
def test_a_non_string_detail_is_rejected(detail: object) -> None:
    assert parse_send_boundary_binding(detail) is None
    assert send_boundary_event_binds(_event(detail), _attempt()) is False


class TestBindingStillRequiresTheRightRecord:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("attempt_id", "ATT-2"),
            ("authorization_id", "AUT-2"),
            ("request_fingerprint", "b" * 64),
            ("account_reference", "ref:other"),
            ("client_order_id", "m085-fedcba9876543210"),
            ("identity_lookup_status", 200),
        ],
    )
    def test_a_well_formed_record_for_something_else_lends_nothing(
        self, field: str, value: object
    ) -> None:
        detail = send_boundary_binding(**{**_FIELDS, field: value})  # type: ignore[arg-type]
        assert parse_send_boundary_binding(detail) is not None, "well-formed by construction"
        assert (
            send_boundary_event_binds(_event(detail), _attempt(), account_reference="ref:account")
            is False
        )

    def test_the_event_must_name_this_attempt(self) -> None:
        assert (
            send_boundary_event_binds(_event(_CANONICAL, attempt_id="ATT-2"), _attempt()) is False
        )

    def test_one_valid_record_among_damaged_ones_still_binds(self) -> None:
        events = [_event(_CANONICAL + " attempt=ATT-2"), _event(_CANONICAL), _event("")]
        assert attempt_may_have_transmitted(_attempt(), events) is True
