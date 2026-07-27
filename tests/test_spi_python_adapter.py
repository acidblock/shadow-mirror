"""PythonAdapter conformance to the LanguageAdapter SPI (P7 extraction).

Fast tier — pure AST, no coverage/pytest subprocess. The integration path
(``build_full_map`` routing through the adapter) is exercised by the existing
``tests/test_map.py`` slow tier, which now runs through ``PythonAdapter`` by
default. Here we pin the boundary contracts directly.
"""

import ast

from shadow_mirror.adapters import PythonAdapter
from shadow_mirror.adapters.python import _expand_executed_lines
from shadow_mirror.spi import (
    Coverage,
    LanguageAdapter,
    ModuleModel,
    Mutant,
)
from shadow_mirror.tree import build_functions, build_tree

_SRC = """
def withdraw(level, amount):
    if amount > level:
        raise ValueError("insufficient stock")
    return level - amount
"""


def _fn(leaf="withdraw"):
    # module_path that does NOT exist on disk: discover/build_* must parse the
    # passed source, never re-read the path.
    return {f.qualname.split(".")[-1]: f for f in build_functions("nope.py", _SRC)}[leaf]


def test_adapter_satisfies_runtime_checkable_protocol():
    a = PythonAdapter()
    assert isinstance(a, LanguageAdapter)
    assert a.language == "python"


def test_discover_parses_source_not_path():
    # 'nope.py' is not on disk; success proves source was parsed, not re-read.
    model = PythonAdapter().discover(_SRC, "nope.py")
    assert isinstance(model, ModuleModel)
    assert {f.qualname for f in model.functions} == {"withdraw"}
    assert [b.kind for b in model.branches] == ["raise"]
    assert model.path == "nope.py"


def test_function_level_mutants_are_well_formed_with_real_linenos():
    a = PythonAdapter()
    fn = _fn()
    for level in ("functional", "behavioral", "observable"):
        muts = a.mutants(level, _SRC, fn)
        assert isinstance(muts, tuple)
        for m in muts:
            assert isinstance(m, Mutant)
            ast.parse(m.mutated_source)  # well-formedness invariant — must parse
            assert fn.lineno <= m.lineno <= fn.end_lineno
    # withdraw has a `level - amount` return (functional) and a `>` compare (behavioral)
    assert a.mutants("functional", _SRC, fn)
    assert a.mutants("behavioral", _SRC, fn)
    assert a.mutants("observable", _SRC, fn) == ()  # no emits


def test_resilient_mutants_synthesize_branch_lineno():
    a = PythonAdapter()
    branch = build_tree("nope.py", _SRC).branches[0]
    muts = a.mutants("resilient", _SRC, branch)
    assert muts and all(isinstance(m, Mutant) for m in muts)
    # lineno is informational for resilient — synthesized from the branch
    assert all(m.lineno == branch.lineno for m in muts)
    for m in muts:
        ast.parse(m.mutated_source)


def test_cross_boundary_types_are_frozen():
    fn = _fn()
    m = PythonAdapter().mutants("functional", _SRC, fn)[0]
    for frozen in (m, Coverage(0, 0, frozenset(), {}), ModuleModel("p", (), ())):
        try:
            object.__setattr__  # sanity
            frozen.__setattr__("x", 1)
        except (AttributeError, TypeError):
            continue
        raise AssertionError(f"{type(frozen).__name__} is not frozen")


# --- executed_lines span-expansion (multi-line-call blind-spot fix) -----------
# coverage.py attributes a multi-line statement to its start line only; the
# adapter must expand so a covered operator on a continuation line is not a false
# gap-unexercised — WITHOUT fabricating lines for statements that never ran.

_MULTILINE = (
    "x = foo(\n"  # 1  statement start (where coverage attributes)
    "    a == b,\n"  # 2  continuation — the `==` operator lives here
    "    c,\n"  # 3  continuation
    ")\n"  # 4  continuation
    "y = 1\n"  # 5  single-line statement
)


def test_expand_attributes_full_span_when_statement_ran():
    # coverage marks only line 1 for the multi-line assign, and line 5.
    out = _expand_executed_lines({1, 5}, _MULTILINE)
    assert {1, 2, 3, 4}.issubset(out)  # whole assign span attributed → L2 `==` covered
    assert 5 in out


def test_expand_true_negative_unexecuted_statement_stays_excluded():
    # REQUIRED true-negative: the multi-line assign never ran (line 1 absent).
    # Its continuation lines must NOT be fabricated — else dead code reads as a
    # gap-unasserted instead of an honest gap-unexercised.
    out = _expand_executed_lines({5}, _MULTILINE)
    assert out == {5}


_COMPOUND = (
    "if (a ==\n"  # 1  if-header start
    "        b):\n"  # 2  continuation of the condition
    "    taken = 1\n"  # 3  body — executed
    "else:\n"  # 4
    "    skipped = 2\n"  # 5  body — NOT executed
)


def test_expand_header_does_not_pull_in_unexecuted_compound_body():
    # The `if` header ran (1) and the taken branch ran (3); the else body (5) did
    # not. Header continuation (2) is attributed; the unexecuted body stays out.
    out = _expand_executed_lines({1, 3}, _COMPOUND)
    assert {1, 2}.issubset(out)  # multi-line condition fully attributed
    assert 5 not in out  # unexecuted else body NOT fabricated


def test_expand_idempotent_on_single_line_statements():
    src = "a = 1\nb = 2\nc = 3\n"
    assert _expand_executed_lines({1, 3}, src) == {1, 3}


def test_expand_returns_raw_on_syntax_error():
    assert _expand_executed_lines({2}, "def (:\n bad") == {2}
