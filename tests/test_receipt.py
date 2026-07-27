"""Conformance tests for ReceiptV1 (docs/receipt-format-v1.md)."""

import json

import pytest

from shadow_mirror import SCHEMA_VERSION, Outcome, Phase, ReceiptV1
from shadow_mirror.receipt import FrozenInstanceError

FIELDS = {
    "schema_version",
    "phase",
    "hypothesis",
    "instrumentation",
    "assertion",
    "outcome",
    "ts",
    "evidence_ref",
}


def make(**override):
    base = dict(
        phase="SM-0",
        hypothesis="the shared counter is not lock-protected",
        instrumentation=("counter_logger",),
        assertion="after == before + 1",
        outcome="verified",
        ts="2026-05-31T15:30:00Z",
        evidence_ref="sha256:abc123",
    )
    base.update(override)
    return ReceiptV1(**base)


def test_defaults_and_normalization():
    r = make()
    assert r.schema_version == SCHEMA_VERSION == "1.0"
    assert r.phase is Phase.SM_0
    assert r.outcome is Outcome.VERIFIED
    assert r.instrumentation == ("counter_logger",)


def test_accepts_enums_or_strings():
    from_strings = make(phase="SM-3", outcome="falsified")
    from_enums = make(phase=Phase.SM_3, outcome=Outcome.FALSIFIED)
    assert from_strings == from_enums


def test_to_dict_shape():
    d = make().to_dict()
    assert set(d) == FIELDS
    assert d["phase"] == "SM-0"  # enum serialized as its string value
    assert d["outcome"] == "verified"
    assert isinstance(d["instrumentation"], list)  # array, not tuple


def test_to_json_sorted_keys():
    text = make().to_json()
    keys = list(json.loads(text).keys())
    assert keys == sorted(keys)


@pytest.mark.parametrize("outcome", ["verified", "falsified", "inconclusive"])
def test_roundtrip_each_outcome(outcome):
    r = make(outcome=outcome)
    assert ReceiptV1.from_json(r.to_json()) == r


def test_roundtrip_empty_instrumentation():
    r = make(instrumentation=())
    assert ReceiptV1.from_json(r.to_json()) == r
    assert r.to_dict()["instrumentation"] == []


def test_is_frozen():
    r = make()
    with pytest.raises(FrozenInstanceError):
        r.phase = Phase.SM_1  # type: ignore[misc]


def test_extra_fields_ignored():
    d = make().to_dict()
    d["extra"] = "ignore me"  # verifier leniency: unknown keys dropped
    assert ReceiptV1.from_dict(d) == make()


def test_invalid_outcome_rejected():
    with pytest.raises(ValueError):
        make(outcome="maybe")


def test_invalid_phase_rejected():
    with pytest.raises(ValueError):
        make(phase="Execute")


def test_non_string_field_rejected():
    with pytest.raises(TypeError):
        make(hypothesis=123)


def test_canonical_spec_example_roundtrips():
    # The exact canonical example from docs/receipt-format-v1.md.
    example = {
        "schema_version": "1.0",
        "phase": "SM-0",
        "hypothesis": (
            "the shared counter is not lock-protected; "
            "two concurrent writers lose one update"
        ),
        "instrumentation": ["counter_logger"],
        "assertion": "for every (thread, before, after) record, after == before + 1",
        "outcome": "verified",
        "ts": "2026-05-31T15:30:00Z",
        "evidence_ref": "sha256:abc123...",
    }
    r = ReceiptV1.from_dict(example)
    assert json.loads(r.to_json()) == example
