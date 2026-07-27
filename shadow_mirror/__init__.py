"""shadow_mirror -- reference data model for the Shadow Mirror methodology.

Composable primitives for the seven-phase scientific-validation loop:

- :class:`Phase` / :data:`PHASES` -- the canonical SM-0..SM-6 enumeration
  (``docs/phases.md``).
- :class:`ReceiptV1` -- the frozen v1 evidence receipt with a sorted-key
  JSON round-trip (``docs/receipt-format-v1.md``).
- :class:`EvidenceBundle` -- a receipt with its canonical map embedded,
  self-verifying (``docs/evidence-bundle.md``).

No runtime dependencies; pure standard library.
"""

from ._version import __version__
from .bundle import EvidenceBundle
from .phases import PHASE_NAMES, PHASES, Phase, name_for
from .receipt import SCHEMA_VERSION, Outcome, ReceiptV1

__all__ = [
    "__version__",
    "Phase",
    "PHASES",
    "PHASE_NAMES",
    "name_for",
    "ReceiptV1",
    "EvidenceBundle",
    "Outcome",
    "SCHEMA_VERSION",
]
