"""Canonical SM-* phase enumeration.

The authoritative in-code reference for the seven-phase Shadow Mirror loop. The
text-form definition in ``docs/phases.md`` conforms to this enum; on any
discrepancy, ``docs/phases.md`` is canonical and the enum is the bug.

    SM-0 -> Hypothesize
    SM-1 -> Instrument
    SM-2 -> Assert
    SM-3 -> Execute
    SM-4 -> Document
    SM-5 -> Review
    SM-6 -> Iterate
"""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    """Phase identifier for one shadow-mirror loop step (SM-0 .. SM-6).

    Each member subclasses ``str``, so ``Phase.SM_3 == "SM-3"`` holds and
    the member serializes directly as its canonical name. The string value
    is the form used in receipts (``ReceiptV1.phase``) and in
    ``docs/phases.md`` -- ``"SM-3"``, never ``"SM_3"`` or the verb.
    """

    SM_0 = "SM-0"  # Hypothesize
    SM_1 = "SM-1"  # Instrument
    SM_2 = "SM-2"  # Assert
    SM_3 = "SM-3"  # Execute
    SM_4 = "SM-4"  # Document
    SM_5 = "SM-5"  # Review
    SM_6 = "SM-6"  # Iterate


#: All phases in canonical order. ``PHASES[0]`` is ``Phase.SM_0``.
PHASES: tuple[Phase, ...] = tuple(Phase)

#: Human-readable verb for each phase, matching ``docs/phases.md``.
PHASE_NAMES: dict[Phase, str] = {
    Phase.SM_0: "Hypothesize",
    Phase.SM_1: "Instrument",
    Phase.SM_2: "Assert",
    Phase.SM_3: "Execute",
    Phase.SM_4: "Document",
    Phase.SM_5: "Review",
    Phase.SM_6: "Iterate",
}


def name_for(phase: Phase | str) -> str:
    """Return the human-readable verb for ``phase`` (e.g. ``"Hypothesize"``).

    Accepts a :class:`Phase` or its string value; raises ``ValueError`` on
    an unknown identifier.
    """
    return PHASE_NAMES[Phase(phase)]
