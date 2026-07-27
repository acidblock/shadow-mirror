"""Adapter SPI — the language boundary (P7).

The operation-tree + receipt + five-level verdict model is **language-agnostic**;
what is language-specific is *parsing*, *mutation*, *coverage ingestion*, and
*test running*. This module is the contract between the two: an engine core that
owns the verdict logic and the wire format, and a per-language ``LanguageAdapter``
that supplies the raw signals.

Derived from evidence, not from Python's shape. Each of the six P7 spikes
(``docs/spikes/P7-*.md``) cleared one capability and surfaced one
silent-correctness trap; those traps are encoded here as **Protocol invariants**,
not left to adapter discretion.

Faithfulness — every method extracts an existing, tested function (the SPI is a
*measured* boundary: the Python engine must factor through it as a pure
extraction). The PythonAdapter that wraps these, and the JsAdapter, are
slice-time work; this file is the boundary they implement.

    LanguageAdapter method        wraps (today)                          module
    ---------------------------   ------------------------------------   ----------
    discover                      build_functions + build_tree           tree.py
    coverage                      run_coverage + run_coverage_with_ctx   _run.py
    mutants("functional", fn)     make_functional_mutants                mutate.py
    mutants("behavioral", fn)     make_behavioral_mutants                mutate.py
    mutants("observable", fn)     make_observable_mutants                mutate.py
    mutants("resilient", branch)  make_mutants                           mutate.py
    timing_tests                  _timing_test_funcs                     map.py
    run_all                       run_tests                              _run.py
    run_selected                  run_selected_tests                     _run.py
    apply                         mutated_file                           _run.py

Scope (v1). Covers **map building** — the five levels + coverage, the only thing
the spikes proved. ``plan`` / ``brief`` / ``delta`` operate on the map (agnostic
data) and need no adapter capability. ``verify`` / ``closure`` (P5) run *candidate*
test code; v1 does not add a capability for them — they reuse ``run_all`` plus an
"apply candidate source" that ``apply`` already generalizes (a candidate is just
a non-mutant source overlay). Noted, not silently omitted.

No separate "operation-tree" capability. The engine's operation tree **is**
:class:`ModuleModel` (functions + branches), which ``discover`` returns; mutation
site-finding walks the adapter's own parse tree directly (one parser, byte
ranges — the node-mapping spike's "trivially clean" join). So a hypothesized
"build an op-tree from tree-sitter" step is a non-item: there is nothing for an
adapter to materialize beyond ``discover`` -> ``ModuleModel``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# FunctionNode / ErrorBranch are core-owned cross-boundary types. They live in
# tree.py today (pure data — the ast computation is only in the build_* helpers);
# the adapter *populates* them, it does not *define* their shape.
from .tree import ErrorBranch, FunctionNode

__all__ = [
    "TestId", "Mutant", "Coverage", "ModuleModel", "LanguageAdapter",
    "LEVELS", "MUTATION_LEVELS", "NODE_ID_FUNCTION", "NODE_ID_BRANCH",
    "SHAPE_HASH_CONTRACT",
]

# --- levels -------------------------------------------------------------------

#: The five rubric-v2 levels, in map column order. Four are mutation-based; one
#: (performant) is detection-based — see ``timing_tests``. Performant being a
#: separate capability, not a ``mutants("performant", …)`` call, encodes the
#: "performant is detection, not mutation" finding structurally
#: (docs/spikes/P7-performant-spike.md).
LEVELS = ("functional", "behavioral", "performant", "resilient", "observable")

#: The four levels for which ``mutants`` is defined. ``functional`` / ``behavioral``
#: / ``observable`` take a :class:`FunctionNode`; ``resilient`` takes an
#: :class:`ErrorBranch` (the engine iterates a function's branches and aggregates
#: across them worst-first). The node type varies by level; the method is uniform.
MUTATION_LEVELS = ("functional", "behavioral", "resilient", "observable")

# --- node identity & shape hash: CORE-specified contract, adapter-computed ----
#
# P7's success criterion is *identical map/receipt/gap-map semantics across two
# languages, one conformance suite*. If node_id and shape_hash were adapter-
# *defined*, two adapters would each work yet emit non-comparable receipts and the
# conformance suite could not pass. So the *scheme* is core-specified; the adapter
# supplies only the language-specific computation behind a fixed contract.

#: A function node's id: ``<module-path>::<dotted-qualname>``.
NODE_ID_FUNCTION = "{path}::{qualname}"
#: An error branch's id: ``<module-path>::<qualname>#<kind>:<ordinal>`` where
#: ``ordinal`` is the Nth branch of that kind in source order within the qualname
#: (stable under reformatting and line shifts; not under reordering).
NODE_ID_BRANCH = "{path}::{qualname}#{kind}:{ordinal}"

#: ``shape_hash`` contract: the first 16 hex chars of a sha256 over the node's
#: structure, **normalized to exclude line numbers and formatting** — a
#: rename-tolerant structural fingerprint (R1). ``ast.dump`` is Python's
#: *implementation* of this contract; a JS adapter uses a normalized tree-sitter
#: S-expression. The contract is "same structure → same hash, cross-checkout";
#: the bytes hashed are the adapter's concern, the *normalization guarantee* is
#: core's.
SHAPE_HASH_CONTRACT = "sha256(normalized-structure, no line numbers)[:16]"

# --- cross-boundary data types (core-owned; adapters populate) ----------------

#: A test identity. **Opaque to the engine** but a hard contract: whatever an
#: adapter puts in :attr:`Coverage.line_tests` and returns from ``timing_tests``
#: MUST be consumable by that same adapter's ``run_selected`` — and the two must
#: be the *same* type, because the performant verdict intersects them
#: (``covering & timing``). For pytest this is a nodeid; for vitest it is a
#: selection-addressable (file, exact-name) — *not* a human display string, which
#: would collide under ``-t`` substring matching
#: (docs/spikes/P7-node-mapping-spike.md, P7-vitest-coverage-spike.md).
TestId = str


@dataclass(frozen=True)
class Mutant:
    """One mutation of a single site.

    INVARIANT (mutation spike, docs/spikes/P7-js-mutation-spike.md): a Mutant is
    **well-formed by construction** — the adapter has re-parsed ``mutated_source``
    and confirmed no parse error before returning it. Byte-splice has no
    ``ast.unparse`` validity guarantee: an unparseable mutant errors the *whole*
    suite → nonzero exit → indistinguishable from a real kill → a false ``proven``.
    The engine trusts that a returned Mutant, when run, fails only if a test
    *detected* it. Malformed candidates are never emitted (drop, do not yield)."""

    label: str            # human-readable, e.g. "op[2]" or "raise-type-swap"
    mutated_source: str   # the full module source with this one site mutated
    lineno: int           # the site's line — the engine gates ``lineno in executed_lines``


@dataclass(frozen=True)
class Coverage:
    """Per-test coverage of a module under its suite.

    INVARIANT (node-mapping spike, docs/spikes/P7-node-mapping-spike.md):
    :attr:`executed_lines` is **full start..end span expanded** — every executed
    statement contributes its whole line range, not just its start line. Start-line
    -only under-resolves multi-line statements, so a covered site on a continuation
    line reads as a false ``gap-unexercised``."""

    covered: int                               # statements/lines covered (for line%)
    num_statements: int                        # total (for line%)
    executed_lines: frozenset[int]             # full-span-expanded executed physical lines
    line_tests: Mapping[int, frozenset[TestId]]  # line → tests that execute it (selection-addressable)


@dataclass(frozen=True)
class ModuleModel:
    """The operation tree of one module: its functions and its error branches.
    Branches are sub-nodes of functions (resilient operates on them)."""

    path: str
    functions: tuple[FunctionNode, ...]
    branches: tuple[ErrorBranch, ...]


# --- the boundary -------------------------------------------------------------


@runtime_checkable
class LanguageAdapter(Protocol):
    """What the engine core requires of a language. Stateless per call; ``cwd`` is
    the project root the target's own suite runs in (the map needs the target's
    test environment — its deps installed, as for running its tests)."""

    #: ``"python"`` | ``"javascript"`` — the receipt records which adapter produced it.
    language: str

    def discover(self, source: str, module_path: str) -> ModuleModel:
        """Parse ``source`` into the operation tree. Populates FunctionNode
        (incl. adapter-computed ``complexity`` — McCabe over the language's tree —
        ``return_lines``, and ``shape_hash`` per the core contract) and ErrorBranch.
        Wraps ``tree.build_functions`` + ``tree.build_tree``."""

    def coverage(self, module_path: str, tests_path: str, cwd: str) -> Coverage:
        """Run the suite under coverage and return per-test attribution. Must honor
        the :class:`Coverage` full-span invariant. Wraps ``_run.run_coverage`` +
        ``_run.run_coverage_with_contexts``."""

    def mutants(self, level: str, source: str, node: FunctionNode | ErrorBranch) -> tuple[Mutant, ...]:
        """Mutants for one ``node`` at one ``level`` (∈ :data:`MUTATION_LEVELS`).
        ``node`` is a FunctionNode for functional/behavioral/observable, an
        ErrorBranch for resilient. Each Mutant honors the well-formedness invariant.
        Empty tuple ⇒ the level yields no signal at this node (→ ``n/a`` /
        ``no-signal``, the engine decides). Wraps the ``make_*_mutants`` family."""

    def timing_tests(self, tests_path: str, cwd: str) -> frozenset[TestId]:
        """The TestIds (same space as :attr:`Coverage.line_tests`) that assert a
        time/resource bound — the performant signal, which is **detection, not
        mutation**. A node is performant-``proven`` iff its covering tests intersect
        this set, else ``n/a``. Takes ``cwd`` (like ``coverage``) so the emitted
        ids carry the *same* path prefix as ``line_tests`` — the intersection is
        uniform, no name/nodeid bridge. Wraps ``map._timing_test_funcs``."""

    def run_all(self, tests_path: str, cwd: str) -> int:
        """Exit code of the whole suite (0 = green). The green-gate /
        regression-guard primitive. Wraps ``_run.run_tests``."""

    def run_selected(self, test_ids: Collection[TestId], cwd: str) -> int:
        """Exit code of just ``test_ids`` (0 = all passed; nonzero = a kill). The
        test-selection primitive the per-test attribution exists to enable. The ids
        MUST be addressable unambiguously (anchored, not substring). Wraps
        ``_run.run_selected_tests``."""

    def apply(self, module_path: str, mutated_source: str) -> AbstractContextManager[None]:
        """Context manager: overlay ``mutated_source`` on ``module_path`` for the
        block, restore on exit — concurrency- and crash-hardened. Generalizes to a
        candidate-source overlay (P5 verify/closure). Wraps ``_run.mutated_file``."""

    def toolchain(self) -> tuple[str, ...]:
        """The instrumentation identity that produced this map — version-stamped,
        language-correct, for the receipt's ``instrumentation`` field. The first
        element is the language (so a JS/TS receipt does not claim ``coverage.py``);
        the rest name the parse + coverage + mutation tools with versions where they
        are knowable in-process (Python package metadata). Out-of-process tools whose
        version lives in the *target* project (e.g. vitest/istanbul in the target's
        node_modules) are named but not pinned here. This is provenance metadata: it
        is NOT hashed into ``evidence_ref`` (which content-addresses the *map* — the
        verdicts — so the same evidence is reproducible across tool upgrades)."""
