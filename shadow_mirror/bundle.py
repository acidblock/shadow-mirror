"""``EvidenceBundle`` -- a receipt with its canonical evidence embedded, self-verifying.

The :class:`~shadow_mirror.receipt.ReceiptV1` is a compact *attestation*: it carries
an ``evidence_ref`` (a sha256 content-address) but not the evidence itself, so reading
it later requires recomputing the map to see the verdicts. An ``EvidenceBundle`` is the
*standalone* form -- the receipt **plus** the canonical map it attests to, in one
artifact -- for the case where the bundle may be the only thing that survives a run
(no map store to recompute against).

It is a wrapper, not a new receipt: ``ReceiptV1`` stays the frozen v1 format
(``docs/receipt-format-v1.md``) untouched. The bundle's value is the **integrity
link** between the two halves:

    bundle.verified  <=>  sha256(canonical(bundle.evidence)) == bundle.receipt.evidence_ref

So a bundle is *self-verifying* and *tamper-evident for inconsistency*: edit the
embedded map, or the receipt's ``evidence_ref``, and ``verified`` goes False. It is
**not** tamper-proof -- an actor who edits the map *and* recomputes a matching
``evidence_ref`` produces a consistent-but-forged bundle. Detecting that needs a
signature over the receipt (a receipt-chain concern, out of scope for v1); ``verified``
attests internal consistency, not authenticity.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from .receipt import ReceiptV1

__all__ = ["EvidenceBundle"]


def _evidence_hash(evidence: Mapping[str, object]) -> str:
    """The evidence's content-address. MUST match ``CoverageMap.evidence_ref``
    byte-for-byte: the same canonical JSON (sorted keys, no whitespace) over the
    same ``canonical_dict``. A drift between the two is caught by any bundle built
    from a real map -- its :attr:`EvidenceBundle.verified` would go False."""
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceBundle:
    """An immutable {receipt, canonical-evidence} pair with a verifiable link."""

    receipt: ReceiptV1
    # The producer's ``canonical_dict()`` (e.g. the CoverageMap). Excluded from
    # ``__hash__`` (a dict is unhashable) but included in equality.
    evidence: Mapping[str, object] = field(hash=False)

    @property
    def verified(self) -> bool:
        """The embedded evidence hashes to the receipt's ``evidence_ref``."""
        return _evidence_hash(self.evidence) == self.receipt.evidence_ref

    # --- serialization (sorted-key JSON round-trip, like ReceiptV1) ----------

    def to_dict(self) -> dict[str, object]:
        return {"receipt": self.receipt.to_dict(), "evidence": dict(self.evidence)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EvidenceBundle:
        return cls(
            receipt=ReceiptV1.from_dict(data["receipt"]),  # type: ignore[arg-type]
            evidence=data["evidence"],  # type: ignore[arg-type]
        )

    @classmethod
    def from_json(cls, text: str) -> EvidenceBundle:
        return cls.from_dict(json.loads(text))
