"""Semantic-coverage map — five levels (rubric v2).

For every function node, a verdict on each level:

- **functional** — mutate the node's ``return`` to ``None``: is the output checked?
- **behavioral** — swap operators in the body: is the logic pinned? (lower bound;
  surviving mutants may include equivalents)
- **performant** — a covering test asserts a time/resource bound, else ``n/a``.
- **resilient** — the P2 error-branch signal, aggregated over the node.
- **observable** — nullify each bare emit (``logger.info(...)`` → ``None``): is the
  emitted signal asserted? (rubric v2; lower bound — emits with side-effecting
  args are skipped, see :func:`~shadow_mirror.mutate._is_emit`)

Mutation runs use **test selection**: only the tests that cover a node (from
coverage dynamic contexts) are rerun per mutant. The map serializes to a
content-addressable :class:`~shadow_mirror.receipt.ReceiptV1` (SM-5), stamped
with ``rubric_version`` so a consumer never infers the level set by counting.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .bundle import EvidenceBundle
from .receipt import ReceiptV1
from .resilient import GAP_UNASSERTED, GAP_UNEXERCISED, NO_SIGNAL, PROVEN

# Signals are obtained through the language adapter (the SPI). ``PythonAdapter``
# is imported lazily inside ``build_full_map`` to avoid an import cycle
# (adapters.python imports ``_timing_test_funcs`` from this module).

NA = "n/a"
RUBRIC_VERSION = 2  # v1 = 4 levels; v2 adds `observable`. Stamped into every map.
LEVELS = ("functional", "behavioral", "performant", "resilient", "observable")
# Worst-first priority for aggregating a node's error branches into one verdict.
_PRIORITY = {GAP_UNASSERTED: 0, NO_SIGNAL: 1, GAP_UNEXERCISED: 2, PROVEN: 3, NA: 4}

# Runtime logging (surfaced by `sm -v/-vv`). INFO = per-node verdict rows; DEBUG =
# per-mutant kill/survive. Silent unless the CLI attaches a handler — a library
# import never logs (no handler, propagation to the root's last-resort only at
# WARNING+). See cli._configure_logging.
log = logging.getLogger(__name__)

__all__ = ["LevelVerdict", "MapNode", "CoverageMap", "build_full_map"]


@dataclass(frozen=True)
class LevelVerdict:
    level: str
    verdict: str
    mutants: int
    killed: int


@dataclass(frozen=True)
class MapNode:
    node_id: str
    qualname: str
    complexity: int
    executed: bool
    levels: tuple[LevelVerdict, ...]


@dataclass(frozen=True)
class CoverageMap:
    module: str
    covered_lines: int
    num_statements: int
    nodes: tuple[MapNode, ...]
    # The instrumentation that produced this map (the adapter's ``toolchain()``):
    # version-stamped + language-correct, used for the receipt's provenance. NOT in
    # ``canonical_dict`` — ``evidence_ref`` content-addresses the verdicts, so the
    # same evidence reproduces across tool upgrades; the toolchain is a receipt-level
    # sibling. The default keeps a directly-constructed map (no adapter) honest as a
    # Python map; ``build_full_map`` overrides it with the real adapter toolchain.
    instrumentation: tuple[str, ...] = ("python", "coverage.py", "sm-mutation")

    def canonical_dict(self) -> dict:
        return {
            "rubric_version": RUBRIC_VERSION,
            "module": self.module,
            "line_coverage": {"covered_lines": self.covered_lines,
                              "num_statements": self.num_statements},
            "nodes": [
                {
                    "node_id": n.node_id,
                    "complexity": n.complexity,
                    "executed": n.executed,
                    "levels": {lv.level: lv.verdict for lv in n.levels},
                }
                for n in sorted(self.nodes, key=lambda n: n.node_id)
            ],
        }

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    def evidence_ref(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def gaps(self) -> list[tuple[str, str, str]]:
        out = []
        for n in sorted(self.nodes, key=lambda n: n.node_id):
            for lv in n.levels:
                if lv.verdict.startswith("gap"):
                    out.append((n.node_id, lv.level, lv.verdict))
        return out

    def to_receipt(self, ts: str) -> ReceiptV1:
        n_gaps = len(self.gaps())
        # Real, language-correct provenance: the adapter's version-stamped toolchain
        # plus the rubric-methodology version (owned by the map, not the adapter).
        return ReceiptV1(
            phase="SM-5",
            hypothesis=f"semantic coverage of {self.module}",
            instrumentation=(*self.instrumentation, f"sm-rubric@v{RUBRIC_VERSION}"),
            assertion=f"{len(self.nodes)} nodes, {n_gaps} level-gaps "
                      f"({sorted(LEVELS)})",
            outcome="verified" if n_gaps == 0 else "inconclusive",
            ts=ts,
            evidence_ref=self.evidence_ref(),
        )

    def to_bundle(self, ts: str) -> EvidenceBundle:
        """The standalone form: this map's receipt with the canonical map embedded,
        self-verifying (``bundle.verified`` ⇔ the embedded map hashes to the receipt's
        ``evidence_ref``). For when the bundle may be the only artifact that survives."""
        return EvidenceBundle(receipt=self.to_receipt(ts), evidence=self.canonical_dict())

    def to_text(self) -> str:
        mark = {PROVEN: "✓", GAP_UNASSERTED: "▲", GAP_UNEXERCISED: "·",
                NA: "–", NO_SIGNAL: "?"}
        head = f"{'function':34} {'cx':>3}  " + "  ".join(f"{lv[:4]:>4}" for lv in LEVELS)
        rows = [f"sm map — {self.module}",
                f"line coverage (coverage.py): {self.covered_lines}/{self.num_statements}",
                "", head, "-" * len(head)]
        for n in sorted(self.nodes, key=lambda n: n.node_id):
            cells = {lv.level: lv.verdict for lv in n.levels}
            marks = "  ".join(f"{mark.get(cells[lv], '?'):>4}" for lv in LEVELS)
            rows.append(f"{n.qualname[:34]:34} {n.complexity:>3}  {marks}")
        gaps = self.gaps()
        rows.append("")
        rows.append(f"{len(gaps)} level-gap(s): " + ", ".join(
            f"{q.split('::')[-1]}/{lvl}" for q, lvl, _ in gaps) if gaps else "no gaps.")
        return "\n".join(rows)


def _timing_test_funcs(tests_path: str) -> set[str]:
    """Names of test functions that assert a time/resource bound."""
    timing = {"perf_counter", "monotonic", "process_time"}
    found: set[str] = set()
    tree = ast.parse(Path(tests_path).read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "benchmark" in {a.arg for a in fn.args.args}:
            found.add(fn.name)
            continue
        for node in ast.walk(fn):
            name = getattr(node, "id", None) or getattr(node, "attr", None)
            if name in timing:
                found.add(fn.name)
                break
    return found


def _kill_count(module_path, mutants, covering, cwd, adapter) -> int:
    killed = 0
    for m in mutants:
        with adapter.apply(module_path, m.mutated_source):
            dead = adapter.run_selected(covering, cwd) != 0
        killed += dead
        log.debug("    branch mutant %s → %s", m.label, "killed" if dead else "survived")
    return killed


def _site_verdict(module_path, mutated_source, lineno, executed_lines, covering, cwd, adapter) -> str:
    """Verdict for ONE mutation site, gated on that site's own line.

    Gating per site (not per node) means a never-run ``return`` reads
    ``gap-unexercised`` even when sibling sites in the same node do run.
    """
    if lineno not in executed_lines:
        return GAP_UNEXERCISED  # this specific line never runs
    if not covering:
        return NO_SIGNAL  # ran, but no covering test resolved
    with adapter.apply(module_path, mutated_source):
        return PROVEN if adapter.run_selected(covering, cwd) != 0 else GAP_UNASSERTED


def _level_verdict(module_path, sited_mutants, executed_lines, covering, cwd, adapter) -> tuple[str, int, int]:
    """Aggregate per-site verdicts **worst-first**: a node is only as proven as
    its weakest site, so a surviving (or never-run) mutant on *any* site is a gap.

    ``sited_mutants`` is ``[(label, mutated_source, lineno), ...]``. This replaces
    the earlier any-killed pooling, which read a node ``proven`` when a *single*
    site was pinned even while its other sites had surviving or unexercised
    mutants. (Resilient keeps its own across-branch worst-first aggregation; see
    ``_resilient_verdict``.)
    """
    if not sited_mutants:
        return NA, 0, 0  # the level does not apply to this node
    verdicts = []
    for m in sited_mutants:
        v = _site_verdict(module_path, m.mutated_source, m.lineno, executed_lines, covering, cwd, adapter)
        log.debug("    site %s @L%d → %s", m.label, m.lineno, v)
        verdicts.append(v)
    worst = min(verdicts, key=lambda v: _PRIORITY.get(v, 9))
    return worst, len(sited_mutants), verdicts.count(PROVEN)


def _mutation_verdict(module_path, mutants, covering, cwd, executed, adapter) -> tuple[str, int, int]:
    """Resilient-branch verdict: ``executed`` is the branch body's run flag.

    Within the branch this is **all-must-die**: the branch is ``proven`` only if
    *every* mutant is killed; a single survivor is ``gap-unasserted``. (Message
    strings are not mutated — see ``mutate._significant_consts`` — so a surviving
    mutant here is a real unasserted constant, not an equivalent-mutant artifact.)
    """
    if not executed:
        return GAP_UNEXERCISED, 0, 0
    if not mutants:
        return NO_SIGNAL, 0, 0  # branch ran but yields no mutant — no signal, not n/a
    if not covering:
        return NO_SIGNAL, len(mutants), 0  # covered but no resolved tests — not a gap
    killed = _kill_count(module_path, mutants, covering, cwd, adapter)
    return (PROVEN if killed == len(mutants) else GAP_UNASSERTED), len(mutants), killed


def _resilient_verdict(module_path, source, branches, cov, covering, cwd, adapter) -> tuple[str, int, int]:
    if not branches:
        return NA, 0, 0
    verdicts, mut, kil = [], 0, 0
    for branch in branches:
        executed = any(ln in cov.executed_lines
                       for ln in range(branch.body_lines[0], branch.body_lines[1] + 1))
        verdict, m, k = _mutation_verdict(module_path, adapter.mutants("resilient", source, branch),
                                          covering, cwd, executed, adapter)
        verdicts.append(verdict)
        mut, kil = mut + m, kil + k
    worst = min(verdicts, key=lambda v: _PRIORITY.get(v, 9))
    return worst, mut, kil


def build_full_map(module_path: str, tests_path: str, cwd: str = ".", adapter=None) -> CoverageMap:
    from .adapters import PythonAdapter  # lazy: avoids the map ↔ adapters import cycle

    adapter = adapter or PythonAdapter()
    cwd = str(Path(cwd).resolve())
    module_rel = Path(os.path.relpath(os.path.abspath(module_path), cwd)).as_posix()
    source = (Path(cwd) / module_rel).read_text(encoding="utf-8")
    parse_path = module_rel if Path(module_rel).exists() else module_path
    model = adapter.discover(source, parse_path)
    functions, all_branches = model.functions, model.branches
    cov = adapter.coverage(module_rel, tests_path, cwd)
    line_tests = cov.line_tests
    timing = adapter.timing_tests(tests_path, cwd)
    log.info("sm map: %s — %d function(s), line coverage %d/%d",
             module_rel, len(functions), cov.covered, cov.num_statements)

    nodes: list[MapNode] = []
    for fn in functions:
        log.debug("  %s (cx %d)", fn.qualname, fn.complexity)
        node_lines = range(fn.lineno, fn.end_lineno + 1)
        executed = any(ln in cov.executed_lines for ln in node_lines)
        covering: set[str] = set()
        for ln in node_lines:
            covering |= line_tests.get(ln, frozenset())

        func_v = _level_verdict(module_rel, adapter.mutants("functional", source, fn),
                                cov.executed_lines, covering, cwd, adapter)
        beh_v = _level_verdict(module_rel, adapter.mutants("behavioral", source, fn),
                               cov.executed_lines, covering, cwd, adapter)
        branches = [b for b in all_branches if fn.lineno <= b.lineno <= fn.end_lineno]
        res_v = _resilient_verdict(module_rel, source, branches, cov, covering, cwd, adapter)
        obs_v = _level_verdict(module_rel, adapter.mutants("observable", source, fn),
                               cov.executed_lines, covering, cwd, adapter)
        # Uniform TestId space (nodeids) — the pre-SPI name/nodeid split bridge is gone.
        perf = PROVEN if covering & timing else NA
        log.info("  %-28s func=%s beha=%s perf=%s resi=%s obse=%s", fn.qualname,
                 func_v[0], beh_v[0], perf, res_v[0], obs_v[0])

        nodes.append(MapNode(
            node_id=fn.node_id if fn.node_id.startswith(module_rel) else f"{module_rel}::{fn.qualname}",
            qualname=fn.qualname, complexity=fn.complexity, executed=executed,
            levels=(
                LevelVerdict("functional", *func_v),
                LevelVerdict("behavioral", *beh_v),
                LevelVerdict("performant", perf, 0, 0),
                LevelVerdict("resilient", *res_v),
                LevelVerdict("observable", *obs_v),
            ),
        ))

    return CoverageMap(module=module_rel, covered_lines=cov.covered,
                       num_statements=cov.num_statements, nodes=tuple(nodes),
                       instrumentation=adapter.toolchain())
