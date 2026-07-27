"""SPIKE → SHIPPED: the emit-assert mutation, now a real level (rubric v2).

This script proved a fifth coverage level — **observable** (*is an emitted
signal asserted?*) — discriminates cleanly. The operator nullifies each bare
emit (``logger.info(...)`` → ``None``); since an emit's return value is unused,
the nullification is data-flow-preserving, so the only test that can die is one
that *observes* the emission.

The implementation is now canonical in the package
(:func:`shadow_mirror.mutate.make_observable_mutants` /
:func:`~shadow_mirror.mutate.observable_site_lines`); this script imports it
rather than carrying a second copy. Run from the repo root:

    python3 docs/spikes/observable_spike.py
"""

from __future__ import annotations

from pathlib import Path

from shadow_mirror._run import run_coverage_with_contexts
from shadow_mirror.map import _level_verdict
from shadow_mirror.mutate import make_observable_mutants
from shadow_mirror.tree import build_functions

ROOT = Path(__file__).resolve().parent.parent.parent
FIX_MOD = "tests/fixtures/observable_demo/service.py"
FIX_TST = "tests/fixtures/observable_demo/test_service.py"


def main() -> None:
    cwd = str(ROOT)
    source = (ROOT / FIX_MOD).read_text(encoding="utf-8")
    functions = build_functions(FIX_MOD)
    cov, line_tests = run_coverage_with_contexts(FIX_MOD, FIX_TST, cwd)

    print(f"observable spike — {FIX_MOD}")
    print(f"{'function':18} {'emits':>5}  {'killed':>6}  observable")
    print("-" * 48)
    for fn in functions:
        node_lines = range(fn.lineno, fn.end_lineno + 1)
        covering: set[str] = set()
        for ln in node_lines:
            covering |= line_tests.get(ln, frozenset())
        mutants = make_observable_mutants(source, fn)
        verdict, n, killed = _level_verdict(
            FIX_MOD, mutants, cov.executed_lines, covering, cwd
        )
        print(f"{fn.qualname:18} {n:>5}  {killed:>6}  {verdict}")


if __name__ == "__main__":
    main()
