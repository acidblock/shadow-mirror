"""``ReceiptV1`` -- the frozen v1 evidence-receipt data model.

Reference implementation of the wire format frozen in
``docs/receipt-format-v1.md``: an eight-field, immutable record with a
sorted-key JSON round-trip. On any discrepancy between this module and that
document, the document is canonical.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass
from enum import Enum

from .phases import Phase

#: The wire-format version this module produces, and the version the
#: round-trip guarantee applies to. See ``docs/receipt-format-v1.md``.
SCHEMA_VERSION = "1.0"

__all__ = ["SCHEMA_VERSION", "Outcome", "ReceiptV1", "FrozenInstanceError"]


class Outcome(str, Enum):
    """The verdict a receipt records -- one of exactly three values.

    A path that merely *executed* is never ``VERIFIED``; verification
    requires an assertion that could have failed and did not. Absent that,
    the honest outcome is ``INCONCLUSIVE``.
    """

    VERIFIED = "verified"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, kw_only=True)
class ReceiptV1:
    """An immutable Shadow Mirror evidence receipt (schema ``"1.0"``).

    Construct with either enums or their string values; both normalize::

        ReceiptV1(
            phase="SM-0",
            hypothesis="the shared counter is not lock-protected",
            assertion="after == before + 1",
            outcome="verified",
            ts="2026-05-31T15:30:00Z",
            evidence_ref="sha256:...",
            instrumentation=("counter_logger",),
        )

    The round-trip guarantee holds for every instance::

        ReceiptV1.from_json(r.to_json()) == r
    """

    phase: Phase
    hypothesis: str
    assertion: str
    outcome: Outcome
    ts: str
    evidence_ref: str
    instrumentation: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        # Normalize then validate. ``object.__setattr__`` because frozen.
        object.__setattr__(self, "phase", Phase(self.phase))
        object.__setattr__(self, "outcome", Outcome(self.outcome))
        object.__setattr__(self, "instrumentation", tuple(self.instrumentation))

        for name in ("hypothesis", "assertion", "ts", "evidence_ref", "schema_version"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be str, got {type(value).__name__}")
        if not all(isinstance(probe, str) for probe in self.instrumentation):
            raise TypeError("instrumentation must be a sequence of str")

    # --- serialization ------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        """Return the canonical mapping: enums as strings, arrays not tuples."""
        return {
            "schema_version": self.schema_version,
            "phase": self.phase.value,
            "hypothesis": self.hypothesis,
            "instrumentation": list(self.instrumentation),
            "assertion": self.assertion,
            "outcome": self.outcome.value,
            "ts": self.ts,
            "evidence_ref": self.evidence_ref,
        }

    def to_json(self) -> str:
        """Serialize to canonical JSON: sorted keys, UTF-8."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReceiptV1:
        """Build from a mapping. Unknown keys are ignored (v1 leniency)."""
        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            phase=data["phase"],  # type: ignore[arg-type]
            hypothesis=data["hypothesis"],  # type: ignore[arg-type]
            instrumentation=tuple(data.get("instrumentation", ())),  # type: ignore[arg-type]
            assertion=data["assertion"],  # type: ignore[arg-type]
            outcome=data["outcome"],  # type: ignore[arg-type]
            ts=data["ts"],  # type: ignore[arg-type]
            evidence_ref=data["evidence_ref"],  # type: ignore[arg-type]
        )

    @classmethod
    def from_json(cls, text: str) -> ReceiptV1:
        """Parse from a JSON string."""
        return cls.from_dict(json.loads(text))
