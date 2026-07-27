"""``sm plan`` — turn the backward-looking gap map into a forward-looking plan.

Pure post-processing over a :class:`~shadow_mirror.map.CoverageMap`: no
subprocess, fully deterministic. For each ``(node, level)`` gap it emits a
ranked, honestly-scaffolded assertion stub.

**Stubs are scaffolds, not oracles.** A stub carries the node's real signature
(placeholder parameter *names*, not callable arguments) and the level's proof
obligation — never a fabricated expected value. A made-up ``== 42`` would poison
grounded generation downstream (P5), so the placeholder ``<EXPECTED>`` is the
honest output.

**Ranking is transparent, not an opaque score.** "Which gap to test first" is a
judgment the tool cannot verify (its real validation is a maintainer agreeing the
top items are genuinely missing — deferred to dogfooding). So the order is a
readable lexicographic sort over surfaced factors, in spec order
(complexity × semantic-coverage deficit), with verdict as a *visible* tiebreak:

1. node **complexity** (higher first)
2. the node's **deficit** — how many applicable levels are gaps (more first)
3. **verdict** — ``gap-unasserted`` (runs, cheap to pin) before ``gap-unexercised``
   (needs a new path); a documented judgment, surfaced so the user can re-sort
4. ``(node_id, level)`` — deterministic final tiebreak (reproducible evidence_ref)

``--diff <base>`` realizes the spec's *changed-in-diff* factor as a **scope**: the
plan is filtered to nodes whose line range intersects the diff (the same
complexity→deficit→verdict order applies within that scope).
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass

from .map import NA, CoverageMap
from .receipt import ReceiptV1
from .resilient import GAP_UNASSERTED, GAP_UNEXERCISED

__all__ = ["PlanItem", "Plan", "build_plan"]

# Verdict tiebreak: unasserted (runs, cheap to pin) before unexercised (needs a
# new path). A documented judgment surfaced in the output — not a hidden weight.
_VERDICT_RANK = {GAP_UNASSERTED: 0, GAP_UNEXERCISED: 1}

_WHY = {
    ("functional", GAP_UNASSERTED): "runs, but the return value is never asserted",
    ("functional", GAP_UNEXERCISED): "the return path never runs under the suite",
    ("behavioral", GAP_UNASSERTED): "an operator swap survives — the logic isn't pinned",
    ("behavioral", GAP_UNEXERCISED): "the operator never runs under the suite",
    ("resilient", GAP_UNASSERTED): "the error branch runs but a mutant survives",
    ("resilient", GAP_UNEXERCISED): "the error branch never runs under the suite",
    ("observable", GAP_UNASSERTED): "the emit runs but no test observes it",
    ("observable", GAP_UNEXERCISED): "the emit line never runs under the suite",
}


@dataclass(frozen=True)
class PlanItem:
    node_id: str
    qualname: str
    level: str
    verdict: str
    complexity: int
    deficit: int  # number of gap levels on this node
    applicable: int  # number of non-n/a levels on this node
    signature: str  # e.g. "charge(<amount>)" — a scaffold, never callable
    stub: str
    why: str

    def sort_key(self) -> tuple:
        return (-self.complexity, -self.deficit,
                _VERDICT_RANK.get(self.verdict, 9), self.node_id, self.level)


@dataclass(frozen=True)
class Plan:
    module: str
    source_evidence_ref: str  # provenance: the map this plan derives from
    items: tuple[PlanItem, ...]
    diff_base: str | None = None  # set when scoped to nodes changed vs a git ref

    def canonical_dict(self) -> dict:
        out = {
            "module": self.module,
            "source_evidence_ref": self.source_evidence_ref,
            "items": [
                {"node_id": it.node_id, "level": it.level, "verdict": it.verdict,
                 "complexity": it.complexity, "deficit": it.deficit,
                 "applicable": it.applicable, "signature": it.signature, "stub": it.stub}
                for it in self.items
            ],
        }
        if self.diff_base is not None:  # omit when absent → non-diff evidence_ref unchanged
            out["diff_base"] = self.diff_base
        return out

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    def evidence_ref(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_receipt(self, ts: str) -> ReceiptV1:
        top = self.items[0] if self.items else None
        assertion = (f"top: {top.qualname}/{top.level} (cx {top.complexity}, "
                     f"deficit {top.deficit}/{top.applicable})") if top else "no gaps"
        scope = f" changed vs {self.diff_base}" if self.diff_base else ""
        return ReceiptV1(
            phase="SM-2",  # generative front-half: predicates proposed, not yet run
            hypothesis=f"test plan for {self.module}: {len(self.items)} ranked "
                       f"(node, level) gaps{scope}",
            instrumentation=("sm-plan",),
            assertion=assertion,
            outcome="inconclusive",
            ts=ts,
            evidence_ref=self.evidence_ref(),
        )

    def to_text(self) -> str:
        scope = f"  scoped to nodes changed vs {self.diff_base}" if self.diff_base else ""
        rows = [f"sm plan — {self.module}{scope}",
                f"{len(self.items)} ranked (node, level) gap(s)  "
                f"[sort: complexity, then deficit, then verdict]", ""]
        if not self.items:
            rows.append("no gaps — nothing to plan.")
            return "\n".join(rows)
        head = f"{'#':>2}  {'cx':>2}  {'deficit':>7}  {'node / level':40}  verdict"
        rows += [head, "-" * len(head)]
        for i, it in enumerate(self.items, 1):
            nl = f"{it.qualname}/{it.level}"
            rows.append(f"{i:>2}  {it.complexity:>2}  {it.deficit:>2}/{it.applicable:<4}  "
                        f"{nl[:40]:40}  {it.verdict}")
        rows += ["", "stubs (scaffolds — fill the <PLACEHOLDERS>, never a fabricated oracle):"]
        for it in self.items:
            rows.append(f"  # {it.qualname}/{it.level} — {it.why}")
            rows.append(f"  {it.stub}")
        return "\n".join(rows)


# --- signature + stub derivation (pure AST, never raises) ----------------


def _signatures(source: str) -> dict[str, ast.AST]:
    """Map ``qualname`` -> its FunctionDef (best-effort; empty on parse error)."""
    try:
        module = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, ast.AST] = {}

    def visit(node: ast.AST, qual: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[".".join(qual + [child.name])] = child
                visit(child, qual + [child.name])
            elif isinstance(child, ast.ClassDef):
                visit(child, qual + [child.name])
            else:
                visit(child, qual)

    visit(module, [])
    return out


def _render_call(qualname: str, fn: ast.AST | None) -> str:
    """``charge(<amount>)`` — placeholder names, not arguments. Never raises."""
    leaf = qualname.split(".")[-1]
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{leaf}(...)"
    try:
        a = fn.args
        parts = [f"<{arg.arg}>" for arg in [*a.posonlyargs, *a.args]
                 if arg.arg not in ("self", "cls")]
        if a.vararg:
            parts.append(f"*{a.vararg.arg}")
        parts += [f"<{arg.arg}>" for arg in a.kwonlyargs]
        if a.kwarg:
            parts.append(f"**{a.kwarg.arg}")
        return f"{leaf}({', '.join(parts)})"
    except Exception:  # pragma: no cover - defensive: a planner must never crash
        return f"{leaf}(...)"


def _exc_type(fn: ast.AST | None) -> str:
    """First raised exception type name in ``fn``, else a placeholder."""
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for node in ast.walk(fn):
            if isinstance(node, ast.Raise) and node.exc is not None:
                target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                if isinstance(target, ast.Name):
                    return target.id
                if isinstance(target, ast.Attribute):
                    return target.attr
    return "<ExcType>"


def _stub(level: str, call: str, fn: ast.AST | None) -> str:
    if level == "functional":
        return f"assert {call} == <EXPECTED>"
    if level == "behavioral":
        return f"assert {call} == <EXACT>  # exact value, not a loose bound"
    if level == "resilient":
        exc = _exc_type(fn)
        if exc == "<ExcType>":  # no `raise` found → an except-handler recovery branch
            return f"assert {call} == <RECOVERED>  # pin the except-branch recovery value"
        return f"with pytest.raises({exc}): {call}"
    if level == "observable":
        return f'assert "<event>" in caplog.text  # after calling {call}'
    return f"# pin {level}: {call}"  # pragma: no cover - all gap levels covered above


def _in_scope(fn: ast.AST | None, changed: set[int] | None) -> bool:
    """Whether a node is in the diff scope. No scope → all in. Unlocatable node
    under a scope → out (we won't claim a node we can't place was changed).

    Conscious edge: ``FunctionDef.lineno`` is the ``def`` line, not the decorator,
    so a change touching *only* a decorator sits above the range and won't scope to
    the node. (Pure-deletion changes likewise produce no new-side lines upstream in
    ``_diff`` and never scope.) Both are acceptable for a changed-node planner.
    """
    if changed is None:
        return True
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    hi = fn.end_lineno or fn.lineno
    return not changed.isdisjoint(range(fn.lineno, hi + 1))


def build_plan(cmap: CoverageMap, source: str, changed_lines: set[int] | None = None,
               diff_base: str | None = None) -> Plan:
    """Rank ``cmap``'s gaps and scaffold a stub for each. Pure; deterministic.

    ``changed_lines`` (from ``_diff.changed_lines``) scopes the plan to nodes that
    intersect a PR's diff; ``diff_base`` records the ref for provenance.
    """
    sigs = _signatures(source)
    items: list[PlanItem] = []
    for node in cmap.nodes:
        fn = sigs.get(node.qualname)
        if not _in_scope(fn, changed_lines):
            continue
        applicable = sum(1 for lv in node.levels if lv.verdict != NA)
        gap_levels = [lv for lv in node.levels if lv.verdict.startswith("gap")]
        call = _render_call(node.qualname, fn)
        for lv in gap_levels:
            items.append(PlanItem(
                node_id=node.node_id, qualname=node.qualname, level=lv.level,
                verdict=lv.verdict, complexity=node.complexity, deficit=len(gap_levels),
                applicable=applicable, signature=call, stub=_stub(lv.level, call, fn),
                why=_WHY.get((lv.level, lv.verdict), "unproven"),
            ))
    items.sort(key=lambda it: it.sort_key())
    return Plan(module=cmap.module, source_evidence_ref=cmap.evidence_ref(),
                items=tuple(items), diff_base=diff_base)
