"""Conformance tests for the SM-* phase enumeration (docs/phases.md)."""

import pytest

from shadow_mirror import PHASE_NAMES, PHASES, Phase, name_for


def test_phase_count_contract():
    # Verbatim from docs/phases.md "Phase count contract".
    assert len(PHASES) == 7
    assert [p.value for p in PHASES] == [
        "SM-0",
        "SM-1",
        "SM-2",
        "SM-3",
        "SM-4",
        "SM-5",
        "SM-6",
    ]


def test_phase_is_str_enum():
    assert Phase.SM_3 == "SM-3"
    assert Phase("SM-3") is Phase.SM_3
    assert Phase(Phase.SM_3) is Phase.SM_3


def test_names_match_verbs():
    assert [PHASE_NAMES[p] for p in PHASES] == [
        "Hypothesize",
        "Instrument",
        "Assert",
        "Execute",
        "Document",
        "Review",
        "Iterate",
    ]
    assert name_for("SM-0") == "Hypothesize"
    assert name_for(Phase.SM_6) == "Iterate"


def test_invalid_phase_rejected():
    with pytest.raises(ValueError):
        Phase("Execute")  # the verb is not the identifier
    with pytest.raises(ValueError):
        Phase("SM_0")  # underscore form is not the wire value
