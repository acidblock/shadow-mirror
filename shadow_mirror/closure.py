"""``check_closure`` — does a candidate test actually close a named gap?

This is the primitive that makes grounded generation trustworthy (P5). A generator
proposes a test to close a ``(node, level)`` gap; this verifies the claim against
the real code before trusting it — the provider-agnostic acceptance contract.

The headline failure it guards against: a **red** candidate vacuously "closes"
every gap. :func:`~shadow_mirror.map.build_full_map` reads only coverage contexts
and mutation kills — it *never* reads pytest's exit code, so a test that fails on
the unmutated module fails under every mutant too, reads as "always killed," and
the cell flips ``proven``. An ungrounded baseline produces exactly such
plausible-but-red tests, so without a green-gate the comparison is inverted —
broken tests win. Hence two gates, in order:

1. **valid** — the *whole combined suite* (existing tests ∪ candidate) is green on
   the unmutated module (checked explicitly here, since the map build cannot tell
   us). This rejects both a red candidate *and* a candidate that breaks a sibling
   test via a module-level side effect — either way some test fails on real code,
   so trusting any "killed" verdict would be vacuous. Precondition: the suite was
   green before; a candidate appended to an already-red suite is ``invalid``.
2. **closed** — only then, the targeted cell moves ``gap → proven`` in a fresh
   map built from suite ∪ candidate.

A legitimate closure is ``valid and closed and not regressions``. The two guards
cover different failure modes: the **green-gate** catches a candidate that breaks
a test's *assertion* (coverage persists), and the **regression guard** catches one
that drops a previously-proven cell's *coverage* — e.g. a candidate test that
shadows a same-named proving suite test (Python keeps the last ``def``).
"""

from __future__ import annotations

import ast
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .map import PROVEN, CoverageMap, build_full_map

__all__ = ["ClosureResult", "JointClosure", "check_closure", "check_joint_closure"]


@dataclass(frozen=True)
class ClosureResult:
    target: tuple[str, str]  # (node_id, level) — the gap the candidate claims to close
    source_map_ref: str  # before_map.evidence_ref() — provenance + stale-map guard
    valid: bool  # the whole combined suite (incl. candidate) is green on real code
    closed: bool  # target cell moved gap → proven
    regressions: tuple[tuple[str, str], ...]  # cells that went proven → not-proven
    before_verdict: str
    after_verdict: str | None
    candidate_tests: tuple[str, ...]
    reason: str  # "" when valid; else why the candidate was rejected
    after_map_ref: str | None = None

    @property
    def legitimate(self) -> bool:
        """The only verdict a generator should trust: green, closed, no collateral."""
        return self.valid and self.closed and not self.regressions


def _verdicts(cmap: CoverageMap) -> dict[tuple[str, str], str]:
    return {(n.node_id, lv.level): lv.verdict for n in cmap.nodes for lv in n.levels}


def _candidate_test_names(candidate_src: str) -> list[str]:
    """Top-level ``test*`` functions in the candidate snippet (what pytest collects)."""
    try:
        tree = ast.parse(candidate_src)
    except SyntaxError:
        return []
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test")]


@contextmanager
def _combined_suite(suite_path: str, candidate_src: str, cwd: str):
    """Write suite ∪ candidate to a temp ``test_*.py`` *beside the suite* (so imports
    and conftest resolve identically), yield its path relative to ``cwd``, clean up."""
    suite_abs = Path(cwd) / suite_path
    body = suite_abs.read_text(encoding="utf-8") + "\n\n" + candidate_src
    fd, tmp = tempfile.mkstemp(prefix="test_smclosure_", suffix=".py",
                               dir=str(suite_abs.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        yield Path(os.path.relpath(tmp, cwd)).as_posix()
    finally:
        os.unlink(tmp)  # never leave a stray test_*.py to pollute the next real run


def check_closure(before_map: CoverageMap, module_path: str, suite_path: str,
                  candidate_src: str, target: tuple[str, str], cwd: str = ".",
                  adapter=None) -> ClosureResult:
    """Verify ``candidate_src`` closes ``target`` (a gap in ``before_map``) honestly.

    ``before_map`` MUST have been built from ``suite_path`` — its ``evidence_ref``
    is stamped into the result so a caller can detect a stale-map mismatch.

    ``adapter`` is the :class:`~shadow_mirror.spi.LanguageAdapter` whose ``run_all``
    runs the green-gate and which ``build_full_map`` re-maps through (default
    ``PythonAdapter``). Three steps here are language-bound; two — the green-gate and
    the re-map — are *adapter-routed*. The third, ``_combined_suite`` (writing
    suite ∪ candidate as a sibling ``test_*.py``), is *deliberately* Python-only:
    candidate-suite combination has no SPI primitive and no non-Python consumer, so
    the adapter boundary stops at run/apply and combination is the documented stop.
    """
    if adapter is None:
        from .adapters import PythonAdapter
        adapter = PythonAdapter()
    before = _verdicts(before_map)
    if target not in before:
        raise ValueError(f"target {target} is not a node/level in the map")
    if not before[target].startswith("gap"):
        raise ValueError(f"target {target} is not a gap (it is {before[target]!r})")

    src_ref = before_map.evidence_ref()
    before_v = before[target]
    names = _candidate_test_names(candidate_src)

    def reject(reason: str) -> ClosureResult:
        return ClosureResult(target, src_ref, valid=False, closed=False, regressions=(),
                             before_verdict=before_v, after_verdict=None,
                             candidate_tests=tuple(names), reason=reason)

    if not names:
        return reject("no-test: candidate defines no top-level test* function")

    with _combined_suite(suite_path, candidate_src, cwd) as combined_rel:
        # Gate 1 — the WHOLE combined suite is green on the unmutated module. The map
        # build ignores pytest's exit code, so a candidate that fails — OR that breaks
        # a sibling via a module-level side effect (coverage persists, the assertion
        # does not) — would read as "always killed → proven" and vacuously close.
        # Gating the whole suite, not just the candidate, closes that dual: a broken
        # sibling fails here too. Precondition: the suite was green before; a candidate
        # appended to an already-red suite is rejected here (the map can't attest it).
        if adapter.run_all(combined_rel, cwd) != 0:
            return reject("suite-not-green: combined suite fails on the unmutated module")
        # Gate 2 — the targeted cell flips gap → proven in a suite ∪ candidate map.
        # build_full_map resolves module_path against the *process* cwd, so hand it
        # an absolute path anchored on our cwd; the suite stays cwd-relative.
        module_abs = str((Path(cwd) / module_path).resolve())
        after_map = build_full_map(module_abs, combined_rel, cwd=cwd, adapter=adapter)

    after = _verdicts(after_map)
    closed = after.get(target) == PROVEN
    regressions = tuple(sorted(
        cell for cell, v in before.items()
        if v == PROVEN and after.get(cell) != PROVEN))
    return ClosureResult(target, src_ref, valid=True, closed=closed, regressions=regressions,
                         before_verdict=before_v, after_verdict=after.get(target),
                         candidate_tests=tuple(names), reason="",
                         after_map_ref=after_map.evidence_ref())


@dataclass(frozen=True)
class JointClosure:
    """Whether *all* accepted candidates are safe **together**, not just each alone."""
    n: int  # number of candidates appended jointly
    valid: bool  # the combined suite (∪ all candidates) is green on real code
    all_closed: bool  # every accepted target is still proven with all candidates present
    regressions: tuple[tuple[str, str], ...]  # baseline-proven cells that dropped
    reason: str  # "" when valid; else why the joint suite was rejected

    @property
    def safe(self) -> bool:
        return self.valid and self.all_closed and not self.regressions


def check_joint_closure(before_map: CoverageMap, module_path: str, suite_path: str,
                        candidate_srcs: list[str], targets: list[tuple[str, str]],
                        cwd: str = ".", adapter=None) -> JointClosure:
    """Verify the *whole accepted set* is jointly safe. Per-candidate closure proves
    each closes its target against the baseline; it does NOT prove the candidates
    don't collide with *each other* (two ``test_helper`` defs, a shared global). This
    appends them all, re-maps once, and checks every target still proven + nothing
    regressed — the single joint gate that makes "N accepted" mean something.

    ``adapter`` threads the same run/apply surface as :func:`check_closure`."""
    if adapter is None:
        from .adapters import PythonAdapter
        adapter = PythonAdapter()
    before = _verdicts(before_map)
    with _combined_suite(suite_path, "\n\n".join(candidate_srcs), cwd) as combined_rel:
        if adapter.run_all(combined_rel, cwd) != 0:
            return JointClosure(len(candidate_srcs), valid=False, all_closed=False,
                                regressions=(), reason="joint-suite-not-green: candidates "
                                "collide on the unmutated module")
        module_abs = str((Path(cwd) / module_path).resolve())
        after = _verdicts(build_full_map(module_abs, combined_rel, cwd=cwd, adapter=adapter))
    all_closed = all(after.get(t) == PROVEN for t in targets)
    regressions = tuple(sorted(
        cell for cell, v in before.items() if v == PROVEN and after.get(cell) != PROVEN))
    return JointClosure(len(candidate_srcs), valid=True, all_closed=all_closed,
                        regressions=regressions, reason="")
