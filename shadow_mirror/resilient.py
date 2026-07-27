"""Resilient-level coverage map (P2 vertical slice).

For each error branch (``raise`` / ``except``) of a module:

- **executed?** — from coverage.py: did the branch's lines run under the suite.
- **asserted?** — from mutation: neutralize/perturb the branch; if any test
  fails, a test pins the branch's behavior.

Verdicts:

- ``proven``          — executed and *every* mutant was killed (all-must-die).
- ``gap-unasserted``  — executed, but at least one mutant survived (NS-1: some
                        aspect of the branch runs and no test would notice it
                        broken). Message strings are not mutated, so a survivor
                        is a real unasserted constant, not equivalent-mutant noise.
- ``gap-unexercised`` — never executed (coverage.py already sees this).
- ``no-signal``       — executed but no mutant could be generated (e.g. bare re-raise).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ._run import mutated_file, run_coverage, run_tests
from .mutate import make_mutants
from .tree import ErrorBranch, build_tree

PROVEN = "proven"
GAP_UNASSERTED = "gap-unasserted"
GAP_UNEXERCISED = "gap-unexercised"
NO_SIGNAL = "no-signal"

__all__ = ["BranchVerdict", "ResilientMap", "build_map", "PROVEN",
           "GAP_UNASSERTED", "GAP_UNEXERCISED", "NO_SIGNAL"]


@dataclass(frozen=True)
class BranchVerdict:
    node_id: str
    kind: str
    qualname: str
    exc_type: str | None
    lineno: int
    executed: bool
    mutants: int
    killed: int
    verdict: str


@dataclass(frozen=True)
class ResilientMap:
    module: str
    covered_lines: int
    num_statements: int
    branches: tuple[BranchVerdict, ...]

    @property
    def line_coverage_pct(self) -> float:
        if not self.num_statements:
            return 100.0
        return round(100.0 * self.covered_lines / self.num_statements, 2)

    @property
    def gaps(self) -> tuple[BranchVerdict, ...]:
        return tuple(b for b in self.branches if b.verdict.startswith("gap"))

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "line_coverage": {
                "covered_lines": self.covered_lines,
                "num_statements": self.num_statements,
                "percent": self.line_coverage_pct,
            },
            "resilient": [vars(b) for b in self.branches],
            "gaps": [b.node_id for b in self.gaps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_text(self) -> str:
        lines = [
            f"sm map — resilient level — {self.module}",
            f"line coverage (coverage.py): {self.covered_lines}/{self.num_statements} "
            f"= {self.line_coverage_pct}%",
            "",
            f"{'verdict':16} {'branch':40} {'exec':5} {'killed/mut'}",
            "-" * 80,
        ]
        mark = {PROVEN: "✓", GAP_UNASSERTED: "▲", GAP_UNEXERCISED: "·", NO_SIGNAL: "?"}
        for b in self.branches:
            short = b.node_id.split("::", 1)[-1]
            lines.append(
                f"{mark.get(b.verdict, ' ')} {b.verdict:14} {short:40} "
                f"{'yes' if b.executed else 'no':5} {b.killed}/{b.mutants}"
            )
        gaps = self.gaps
        lines.append("")
        if gaps:
            lines.append(f"{len(gaps)} resilient gap(s) — error paths line coverage calls covered "
                         f"but no test proves:")
            for b in gaps:
                why = "runs, unproven" if b.verdict == GAP_UNASSERTED else "never exercised"
                lines.append(f"  ▲ {b.node_id.split('::', 1)[-1]}  ({b.exc_type or '?'}, {why})")
        else:
            lines.append("no resilient gaps.")
        return "\n".join(lines)


def _executed(branch: ErrorBranch, executed_lines: frozenset[int]) -> bool:
    start, end = branch.body_lines
    return any(line in executed_lines for line in range(start, end + 1))


def build_map(module_path: str, tests_path: str, cwd: str = ".") -> ResilientMap:
    """Legacy single-level (resilient-only) map — kept, *not* factored behind the SPI.

    A conscious keep decision (P7): this is the original P2 whole-suite-per-mutant
    surface (every mutant runs the entire ``tests_path`` via ``run_tests`` — no
    per-test coverage context, no selection). :func:`shadow_mirror.map.build_full_map`
    supersedes it for the five-level map and routes through a ``LanguageAdapter``.
    This function is retained as-is because ``tests/test_engine.py`` pins its
    behavior and it documents the pre-adapter baseline; threading a ``PythonAdapter``
    through it would add indirection with no second consumer. Not deprecated, not
    extended — the legacy whole-suite surface.
    """
    cwd = str(Path(cwd).resolve())
    tree = build_tree(module_path)
    cov = run_coverage(module_path, tests_path, cwd)
    source = Path(module_path).read_text(encoding="utf-8")

    verdicts: list[BranchVerdict] = []
    for branch in tree.branches:
        executed = _executed(branch, cov.executed_lines)
        mutants = make_mutants(source, branch) if executed else []
        killed = 0
        if executed and mutants:
            for _label, mutated_source in mutants:
                with mutated_file(module_path, mutated_source):
                    if run_tests(tests_path, cwd) != 0:
                        killed += 1

        if not executed:
            verdict = GAP_UNEXERCISED
        elif not mutants:
            verdict = NO_SIGNAL
        elif killed == len(mutants):
            verdict = PROVEN  # all-must-die: every mutant on the branch was killed
        else:
            verdict = GAP_UNASSERTED  # a surviving (significant) mutant is a gap

        verdicts.append(
            BranchVerdict(
                node_id=branch.node_id, kind=branch.kind, qualname=branch.qualname,
                exc_type=branch.exc_type, lineno=branch.lineno, executed=executed,
                mutants=len(mutants), killed=killed, verdict=verdict,
            )
        )

    return ResilientMap(
        module=module_path, covered_lines=cov.covered,
        num_statements=cov.num_statements, branches=tuple(verdicts),
    )
