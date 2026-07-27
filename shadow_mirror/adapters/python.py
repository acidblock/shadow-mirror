"""PythonAdapter — the reference :class:`LanguageAdapter` (P7 extraction).

A *pure extraction*: every method wraps an existing, tested function (the
faithfulness table in ``spi.py``). The engine factoring through this adapter
produces byte-identical maps to the pre-SPI direct calls — that equivalence is
how the SPI proves it is well-shaped. Two pre-SPI hacks were removed in the
process (see module-level notes below).
"""

from __future__ import annotations

import ast
import importlib.metadata as _md
from collections.abc import Collection
from contextlib import AbstractContextManager
from pathlib import Path

from .._version import __version__ as _SM_VERSION

from .._run import (
    mutated_file,
    run_coverage_with_contexts,
    run_selected_tests,
    run_tests,
)
from ..map import _timing_test_funcs
from ..mutate import (
    make_behavioral_mutants,
    make_functional_mutants,
    make_mutants,
    make_observable_mutants,
)
from ..spi import Coverage, ErrorBranch, FunctionNode, ModuleModel, Mutant, TestId
from ..tree import build_functions, build_tree

# Per-level dispatch for the function-scoped mutators. ``resilient`` is handled
# separately (it operates on an ErrorBranch and its generator returns 2-tuples).
_FUNCTION_MUTATORS = {
    "functional": make_functional_mutants,
    "behavioral": make_behavioral_mutants,
    "observable": make_observable_mutants,
}


def _expand_executed_lines(raw: Collection[int], source: str) -> frozenset[int]:
    """Satisfy the ``Coverage.executed_lines`` invariant: a statement whose *own*
    code executed contributes its whole physical line range.

    ``coverage.py`` attributes a multi-line statement to its start line only, so a
    covered operator on a *continuation* line (e.g. an ``==`` argument inside a
    multi-line call) would otherwise be absent from ``executed_lines`` and read as
    a false ``gap-unexercised`` — un-closable by any test. A statement's *own*
    lines are its full span MINUS the spans of every statement nested within it,
    so an executed compound-statement header (``if``/``for``/``try`` …) never drags
    in an unexecuted body — which would mislabel genuinely dead code as
    ``gap-unasserted`` instead of ``gap-unexercised``. Only when a statement's own
    code actually ran does its full range join the set.
    """
    raw = frozenset(raw)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return raw  # malformed source: trust coverage's raw attribution, expand nothing
    expanded = set(raw)
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        own = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        for desc in ast.walk(node):
            if desc is node or not isinstance(desc, ast.stmt):
                continue
            own -= set(range(desc.lineno, (desc.end_lineno or desc.lineno) + 1))
        if own & raw:  # the statement's own code ran → attribute its whole span
            expanded |= own
    return frozenset(expanded)


class PythonAdapter:
    """Implements :class:`shadow_mirror.spi.LanguageAdapter` for Python."""

    language = "python"

    def discover(self, source: str, module_path: str) -> ModuleModel:
        # Parses the provided ``source`` (no redundant re-read / TOCTOU); ``path``
        # still backs node_id + filename.
        functions = build_functions(module_path, source)
        branches = build_tree(module_path, source).branches
        return ModuleModel(path=module_path, functions=functions, branches=branches)

    def coverage(self, module_path: str, tests_path: str, cwd: str) -> Coverage:
        cov, line_tests = run_coverage_with_contexts(module_path, tests_path, cwd)
        # Satisfy the Coverage.executed_lines invariant (full start..end span
        # expanded). coverage.py reports start-line-only; expand against the source
        # it ran on so continuation-line operators are not false gap-unexercised.
        source = (Path(cwd) / module_path).read_text(encoding="utf-8")
        return Coverage(
            covered=cov.covered,
            num_statements=cov.num_statements,
            executed_lines=_expand_executed_lines(cov.executed_lines, source),
            line_tests=line_tests,
        )

    def mutants(self, level: str, source: str, node: FunctionNode | ErrorBranch) -> tuple[Mutant, ...]:
        if level == "resilient":
            # ``make_mutants`` returns (label, src) per branch — no per-site line.
            # ``lineno`` is synthesized from the branch and is *informational* for
            # resilient: the engine gates resilient on the branch's ``body_lines``,
            # not this field (see spi.Mutant contract).
            return tuple(
                Mutant(label=label, mutated_source=src, lineno=node.lineno)
                for label, src in make_mutants(source, node)
            )
        mutator = _FUNCTION_MUTATORS[level]
        return tuple(
            Mutant(label=label, mutated_source=src, lineno=lineno)
            for label, src, lineno in mutator(source, node)
        )

    def timing_tests(self, tests_path: str, cwd: str) -> frozenset[TestId]:
        # Read the test file via ``cwd`` (the scan needs an absolute path), but emit
        # nodeids prefixed with the *relative* ``tests_path`` — the SAME TestId space
        # as ``Coverage.line_tests`` (``_run._ctx_to_nodeid`` uses the relative path).
        # So the engine's performant check is a uniform ``covering & timing`` with no
        # name/nodeid bridge.
        names = _timing_test_funcs(str(Path(cwd) / tests_path))
        return frozenset(f"{tests_path}::{name}" for name in names)

    def run_all(self, tests_path: str, cwd: str) -> int:
        return run_tests(tests_path, cwd)

    def run_selected(self, test_ids: Collection[TestId], cwd: str) -> int:
        return run_selected_tests(sorted(test_ids), cwd)

    def apply(self, module_path: str, mutated_source: str) -> AbstractContextManager[None]:
        return mutated_file(module_path, mutated_source)

    def toolchain(self) -> tuple[str, ...]:
        return (
            "python",
            f"coverage.py@{_pkg_version('coverage')}",
            f"sm-mutation@{_SM_VERSION}",
        )


def _pkg_version(name: str) -> str:
    try:
        return _md.version(name)
    except _md.PackageNotFoundError:  # pragma: no cover - defensive (always installed in-env)
        return "unknown"
