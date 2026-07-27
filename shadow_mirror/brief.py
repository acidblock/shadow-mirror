"""``build_brief`` — turn a :class:`~shadow_mirror.plan.Plan` into a generation
brief: the artifact a test generator (any model, any vendor) consumes, plus the
**acceptance contract** that decides whether what it produces is trusted.

The contract is the point. Shadow Mirror does not take a generated test's word
that it closes a gap — it *verifies* the claim with
:func:`~shadow_mirror.closure.check_closure`. So the brief is provider-agnostic:
it states the proof obligation per gap and the machine-checkable acceptance
predicate, and carries no fabricated oracle a generator could pattern-match to a
plausible-but-wrong value.

Provenance is a chain — ``map_ref → plan_ref → brief_ref`` — so a downstream
artifact (a generated test, a closure receipt) is auditably tied back to the exact
map it was planned from. ``map_ref`` is read from the plan's
``source_evidence_ref`` (a plan already binds to its map), so a brief is built from
the plan alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .plan import Plan

__all__ = ["GapBrief", "GenerationBrief", "build_brief", "ACCEPTANCE"]

# The C4 contract, verbatim into every brief. A generator is told exactly how its
# output is judged — verification-defined, not oracle-on-faith.
ACCEPTANCE = (
    "A candidate test is ACCEPTED for a gap iff ALL hold, checked by "
    "shadow_mirror.closure.check_closure: (1) VALID — it is green on the "
    "unmutated module (a red test that merely fails everywhere is rejected, not "
    "credited); (2) CLOSED — appending it to the suite flips the target cell "
    "gap→proven under sm map; (3) NO REGRESSION — no previously-proven cell drops. "
    "Write the assertion that the proof obligation demands; do not invent an "
    "expected value you cannot justify from the code."
)

# What "proven" demands per level — i.e. which mutation the test must make fail.
_OBLIGATION = {
    "functional": "assert the exact return value; a return→None mutation must fail the test",
    "behavioral": "assert the exact value, not a loose bound; an operator swap must fail the test",
    "resilient": "pin the error path (pytest.raises, or the recovered value); removing the "
                 "raise/handler must fail the test",
    "observable": "assert the emitted log/metric (e.g. caplog); nullifying the emit must fail the test",
    "performant": "assert a time or resource bound",
}


@dataclass(frozen=True)
class GapBrief:
    node_id: str
    qualname: str
    level: str
    verdict: str
    signature: str  # scaffold call, e.g. "charge(<amount>)" — never callable
    stub: str  # the assertion skeleton with <PLACEHOLDER>s
    obligation: str  # what the level's proof requires
    why: str

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "level": self.level, "verdict": self.verdict,
                "signature": self.signature, "stub": self.stub,
                "obligation": self.obligation, "why": self.why}


@dataclass(frozen=True)
class GenerationBrief:
    module: str
    map_ref: str  # provenance: the CoverageMap the plan derived from
    plan_ref: str  # provenance: the Plan this brief derived from
    gaps: tuple[GapBrief, ...]
    diff_base: str | None = None

    def canonical_dict(self) -> dict:
        out = {
            "module": self.module,
            "map_ref": self.map_ref,
            "plan_ref": self.plan_ref,
            "acceptance": ACCEPTANCE,
            "gaps": [g.as_dict() for g in self.gaps],
        }
        if self.diff_base is not None:
            out["diff_base"] = self.diff_base
        return out

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    def evidence_ref(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_prompt(self) -> str:
        """The thin prompt contract: ranked gaps + obligations + acceptance. No
        fabricated oracle; the generator fills each assertion from the code."""
        scope = f" (changed vs {self.diff_base})" if self.diff_base else ""
        rows = [f"Write pytest tests that close these semantic-coverage gaps in "
                f"{self.module}{scope}, highest-priority first.", "",
                "ACCEPTANCE", ACCEPTANCE, "", "GAPS"]
        for i, g in enumerate(self.gaps, 1):
            rows += [
                f"{i}. {g.qualname} / {g.level} ({g.verdict}) — {g.why}",
                f"   call:       {g.signature}",
                f"   obligation: {g.obligation}",
                f"   stub:       {g.stub}",
            ]
        if not self.gaps:
            rows.append("(no gaps — nothing to generate)")
        return "\n".join(rows)


def build_brief(plan: Plan) -> GenerationBrief:
    """Derive a generation brief from a plan. Pure; deterministic. The plan already
    binds to its map (``source_evidence_ref``), so the full provenance chain is
    recoverable from the plan alone."""
    gaps = tuple(
        GapBrief(node_id=it.node_id, qualname=it.qualname, level=it.level,
                 verdict=it.verdict, signature=it.signature, stub=it.stub,
                 obligation=_OBLIGATION.get(it.level, "pin the level's behavior"),
                 why=it.why)
        for it in plan.items
    )
    return GenerationBrief(module=plan.module, map_ref=plan.source_evidence_ref,
                           plan_ref=plan.evidence_ref(), gaps=gaps,
                           diff_base=plan.diff_base)
