"""``sm verify`` — the grounded-generation acceptance gate (P5 increment 2).

The vendor-free realization of the headline: a brief (``sm plan --brief``) is the
prompt; an agent writes candidate tests; this verifies each against the real code
via :func:`~shadow_mirror.closure.check_closure` and reports which *legitimately*
close which gaps. No model is embedded — generation is delegated, acceptance is
mechanical (C1/C4). Nothing auto-merges; the report is proposals + verdicts.

Two layers of verification:

- **per-proposal** — each candidate is checked independently against the *baseline*
  suite + map (no order effects). A proposal is ``accepted`` iff its closure is
  legitimate (green, closes its target, no regression).
- **joint** — when ≥2 proposals are accepted, one final gate appends them *all* and
  re-maps once. Independent acceptance does NOT certify the set is jointly safe:
  two candidates can each close their target yet collide (a shared global, two
  same-named tests). ``joint.safe`` is what makes "N accepted" mean something.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .closure import JointClosure, check_closure, check_joint_closure
from .map import CoverageMap
from .receipt import ReceiptV1

__all__ = ["Proposal", "Verdict", "VerificationReport", "verify_proposals"]


@dataclass(frozen=True)
class Proposal:
    node_id: str
    level: str
    candidate_src: str
    label: str = ""

    @property
    def target(self) -> tuple[str, str]:
        return (self.node_id, self.level)


@dataclass(frozen=True)
class Verdict:
    node_id: str
    level: str
    label: str
    accepted: bool  # the closure is legitimate (green, closed, no regression)
    valid: bool
    closed: bool
    regressions: tuple[tuple[str, str], ...]
    reason: str  # "" when accepted; else why rejected

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "level": self.level, "label": self.label,
                "accepted": self.accepted, "valid": self.valid, "closed": self.closed,
                "regressions": [list(c) for c in self.regressions], "reason": self.reason}


@dataclass(frozen=True)
class VerificationReport:
    module: str
    map_ref: str  # provenance: the baseline CoverageMap every proposal was checked against
    verdicts: tuple[Verdict, ...]
    joint: JointClosure | None  # set when ≥2 proposals were accepted

    @property
    def accepted(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.accepted)

    @property
    def all_clear(self) -> bool:
        """Every proposal accepted AND (if checked) the accepted set is jointly safe."""
        if not self.verdicts or any(not v.accepted for v in self.verdicts):
            return False
        return self.joint is None or self.joint.safe

    def canonical_dict(self) -> dict:
        out: dict = {"module": self.module, "map_ref": self.map_ref,
                     "verdicts": [v.as_dict() for v in self.verdicts]}
        if self.joint is not None:
            out["joint"] = {"n": self.joint.n, "valid": self.joint.valid,
                            "all_closed": self.joint.all_closed, "safe": self.joint.safe,
                            "regressions": [list(c) for c in self.joint.regressions],
                            "reason": self.joint.reason}
        return out

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    def evidence_ref(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_receipt(self, ts: str) -> ReceiptV1:
        n_acc = len(self.accepted)
        joint = "" if self.joint is None else (
            " jointly-safe" if self.joint.safe else " JOINT-UNSAFE")
        return ReceiptV1(
            phase="SM-5",
            hypothesis=f"grounded test proposals for {self.module}",
            instrumentation=("sm-closure",),
            assertion=f"{n_acc}/{len(self.verdicts)} proposals accepted{joint}",
            outcome="verified" if self.all_clear else "inconclusive",
            ts=ts,
            evidence_ref=self.evidence_ref(),
        )

    def to_text(self) -> str:
        rows = [f"sm verify — {self.module}",
                f"{len(self.accepted)}/{len(self.verdicts)} proposals accepted", ""]
        head = f"{'':>2}  {'node / level':40}  {'verdict':9}  detail"
        rows += [head, "-" * len(head)]
        for i, v in enumerate(self.verdicts, 1):
            mark = "ACCEPT" if v.accepted else "reject"
            detail = "legitimate closure" if v.accepted else v.reason
            rows.append(f"{i:>2}  {(v.node_id.split('::')[-1] + '/' + v.level)[:40]:40}  "
                        f"{mark:9}  {detail}")
        if self.joint is not None:
            verdict = "SAFE" if self.joint.safe else "UNSAFE"
            extra = self.joint.reason or (f"regressions: {self.joint.regressions}"
                                          if self.joint.regressions else "all targets hold")
            rows += ["", f"joint check ({self.joint.n} accepted together): {verdict} — {extra}"]
        return "\n".join(rows)


def _validate(cmap: CoverageMap, p: Proposal) -> str:
    """Return a rejection reason if the proposal's target isn't a closable gap, else ""."""
    cells = {(n.node_id, lv.level): lv.verdict for n in cmap.nodes for lv in n.levels}
    if p.target not in cells:
        return f"unknown-target: {p.node_id}/{p.level} is not in the map"
    if not cells[p.target].startswith("gap"):
        return f"not-a-gap: {p.node_id}/{p.level} is {cells[p.target]!r}"
    return ""


def verify_proposals(cmap: CoverageMap, module_path: str, suite_path: str,
                     proposals: list[Proposal], cwd: str = ".",
                     adapter=None) -> VerificationReport:
    """Verify each proposal independently against ``cmap``'s baseline, then jointly.

    ``cmap`` is the baseline map (built once by the caller) — the single provenance
    anchor every closure is checked against; ``map_ref`` records it. ``adapter`` is
    forwarded to the closure checks (the run/apply surface); default ``PythonAdapter``.
    """
    verdicts: list[Verdict] = []
    for p in proposals:
        bad = _validate(cmap, p)
        if bad:
            verdicts.append(Verdict(p.node_id, p.level, p.label, accepted=False,
                                    valid=False, closed=False, regressions=(), reason=bad))
            continue
        c = check_closure(cmap, module_path, suite_path, p.candidate_src, p.target, cwd, adapter)
        verdicts.append(Verdict(
            p.node_id, p.level, p.label, accepted=c.legitimate, valid=c.valid,
            closed=c.closed, regressions=c.regressions,
            reason="" if c.legitimate else (c.reason or _why_rejected(c)),
        ))

    accepted = [(v, p) for v, p in zip(verdicts, proposals) if v.accepted]
    joint: JointClosure | None = None
    if len(accepted) >= 2:  # 1 accepted ⇒ joint == independent; skip the extra map build
        joint = check_joint_closure(
            cmap, module_path, suite_path,
            [p.candidate_src for _v, p in accepted],
            [(v.node_id, v.level) for v, _p in accepted], cwd, adapter)
    return VerificationReport(module=cmap.module, map_ref=cmap.evidence_ref(),
                              verdicts=tuple(verdicts), joint=joint)


def _why_rejected(c) -> str:
    if not c.closed:
        return "valid but does not close the target"
    if c.regressions:
        return f"closes target but regresses {list(c.regressions)}"
    return "rejected"
