"""Mechanism tests for ``check_closure`` — the P5 grounded-generation acceptance
gate. The centerpiece is ``test_red_candidate_is_invalid``: a covering-but-red
test must NOT be allowed to vacuously close a gap.

The subprocess tests build a real module + suite in ``tmp_path`` so coverage and
mutation run for real (``@pytest.mark.slow``). The validation/no-test paths reject
before any subprocess, so they run fast against a hand-built map.
"""

import pytest

from shadow_mirror.closure import check_closure
from shadow_mirror.map import (
    NA,
    PROVEN,
    CoverageMap,
    LevelVerdict,
    MapNode,
    build_full_map,
)
from shadow_mirror.resilient import GAP_UNASSERTED

# --- fast paths: hand-built maps, no subprocess ---------------------------

_LEVELS = ("functional", "behavioral", "performant", "resilient", "observable")


def _node(qualname, **verdicts):
    levels = tuple(LevelVerdict(lv, verdicts.get(lv, NA), 0, 0) for lv in _LEVELS)
    return MapNode(node_id=f"m.py::{qualname}", qualname=qualname,
                   complexity=1, executed=True, levels=levels)


def _map(*nodes):
    return CoverageMap(module="m.py", covered_lines=1, num_statements=1, nodes=nodes)


def test_target_not_in_map_raises():
    cmap = _map(_node("charge", functional=GAP_UNASSERTED))
    with pytest.raises(ValueError):
        check_closure(cmap, "m.py", "t.py", "def test_x(): pass",
                      ("m.py::ghost", "functional"))


def test_target_that_is_not_a_gap_raises():
    cmap = _map(_node("charge", functional=PROVEN))
    with pytest.raises(ValueError):
        check_closure(cmap, "m.py", "t.py", "def test_x(): pass",
                      ("m.py::charge", "functional"))


def test_candidate_with_no_test_is_invalid():
    cmap = _map(_node("charge", functional=GAP_UNASSERTED))
    res = check_closure(cmap, "m.py", "t.py", "helper = 1  # not a test",
                        ("m.py::charge", "functional"))
    assert not res.valid and not res.closed
    assert res.reason.startswith("no-test")
    assert res.source_map_ref == cmap.evidence_ref()  # provenance stamped even on reject


# --- subprocess paths: real module + suite in tmp_path --------------------


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    # The engine runs mutation subprocesses against module_rel resolved from the
    # *process* cwd, so the test must chdir into the target dir — exactly how a
    # user invokes `sm` from inside their repo.
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write(in_tmp, module_src, suite_src):
    (in_tmp / "bank.py").write_text(module_src, encoding="utf-8")
    (in_tmp / "test_bank.py").write_text(suite_src, encoding="utf-8")
    # build_full_map resolves module_path against the process cwd, so pass it
    # absolute; the suite path is relative to the subprocess cwd (in_tmp).
    return build_full_map(str(in_tmp / "bank.py"), "test_bank.py", cwd=str(in_tmp))


def _target(cmap, qualname, level):
    node = next(n for n in cmap.nodes if n.qualname == qualname)
    return (node.node_id, level)


_GUARDED = (
    "def charge(amount):\n"
    "    if amount <= 0:\n"
    '        raise ValueError("bad")\n'
    "    return amount * 2\n"
)
_RUNS_NO_ASSERT = "import bank\n\n\ndef test_runs():\n    bank.charge(5)\n"


@pytest.mark.slow
def test_green_value_aware_candidate_closes_functional(in_tmp):
    before = _write(in_tmp, _GUARDED, _RUNS_NO_ASSERT)
    target = _target(before, "charge", "functional")
    assert before.canonical_dict()  # sanity
    candidate = "def test_value():\n    import bank\n    assert bank.charge(5) == 10\n"
    res = check_closure(before, "bank.py", "test_bank.py", candidate, target,
                        cwd=str(in_tmp))
    assert res.valid and res.closed and not res.regressions
    assert res.legitimate
    assert res.after_verdict == PROVEN
    assert res.source_map_ref == before.evidence_ref()
    assert res.after_map_ref and res.after_map_ref != res.source_map_ref


@pytest.mark.slow
def test_red_candidate_is_invalid(in_tmp):
    # CENTERPIECE — a covering test that FAILS on the unmutated module must not
    # vacuously close. build_full_map ignores pytest's exit code, so without the
    # green-gate this candidate reads as "always killed" → proven. The gate makes
    # it `invalid`, the difference between grounding and laundering broken tests.
    before = _write(in_tmp, _GUARDED, _RUNS_NO_ASSERT)
    target = _target(before, "charge", "functional")
    candidate = "def test_red():\n    import bank\n    assert bank.charge(5) == 999\n"
    res = check_closure(before, "bank.py", "test_bank.py", candidate, target,
                        cwd=str(in_tmp))
    assert not res.valid
    assert not res.closed
    assert not res.legitimate
    assert res.reason.startswith("suite-not-green")  # the red test makes the suite red


@pytest.mark.slow
def test_candidate_breaking_a_sibling_via_global_is_not_legitimate(in_tmp):
    # The dual of the red-test bug. The candidate is green *in isolation* but a
    # module-level side effect (bank.RATE = 0) breaks the suite's proving test_add.
    # add's line still EXECUTES (coverage persists) so no proven→gap regression
    # fires — only a WHOLE-SUITE green-gate catches it. Selected-candidate gating
    # would report this legitimate. This is why Gate 1 runs the whole suite.
    module = ("RATE = 1\n\n\ndef add(a, b):\n    return (a + b) * RATE\n\n\n"
              "def mul(a, b):\n    return a * b\n")
    suite = ("import bank\n\n\ndef test_add():\n    assert bank.add(2, 3) == 5\n\n\n"
             "def test_mul_runs():\n    bank.mul(2, 3)\n")
    before = _write(in_tmp, module, suite)
    target = _target(before, "mul", "functional")
    candidate = ("import bank\nbank.RATE = 0\n\n\n"
                 "def test_mul():\n    import bank\n    assert bank.mul(2, 3) == 6\n")
    res = check_closure(before, "bank.py", "test_bank.py", candidate, target,
                        cwd=str(in_tmp))
    assert not res.valid  # the side effect breaks test_add → suite not green
    assert not res.legitimate
    assert res.reason.startswith("suite-not-green")


@pytest.mark.slow
def test_value_blind_candidate_does_not_close_behavioral(in_tmp):
    # `is not None` kills return→None (so it WOULD close functional) but survives
    # the operator swap (charge(5)/2 = 2.5 is still not None) → behavioral stays a
    # gap. Targeting behavioral is what makes this test meaningful (advisor catch).
    before = _write(in_tmp, _GUARDED, _RUNS_NO_ASSERT)
    target = _target(before, "charge", "behavioral")
    assert before.canonical_dict()["nodes"][0]["levels"]["behavioral"].startswith("gap")
    candidate = ("def test_blind():\n    import bank\n"
                 "    assert bank.charge(5) is not None\n")
    res = check_closure(before, "bank.py", "test_bank.py", candidate, target,
                        cwd=str(in_tmp))
    assert res.valid  # green on real code
    assert not res.closed  # but does not pin the operator
    assert not res.legitimate


@pytest.mark.slow
def test_closing_target_while_shadowing_a_proving_test_is_not_legitimate(in_tmp):
    # The regression guard. Two independent nodes: `add` is proven, `mul` is a gap.
    # The candidate closes mul AND appends a second `test_add` that shadows the
    # suite's proving test (Python keeps the last def) — so add regresses
    # proven→gap. closed=True but regressions≠() → legitimate=False. This is the
    # concatenation-artifact / name-collision catch.
    module = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    suite = (
        "import bank\n\n\n"
        "def test_add():\n    assert bank.add(2, 3) == 5\n\n\n"
        "def test_mul_runs():\n    bank.mul(2, 3)\n"
    )
    before = _write(in_tmp, module, suite)
    add_fn = _target(before, "add", "functional")
    add_node = next(n for n in before.nodes if n.qualname == "add")
    assert {lv.level: lv.verdict for lv in add_node.levels}["functional"] == PROVEN
    target = _target(before, "mul", "functional")
    candidate = (
        "def test_mul():\n    import bank\n    assert bank.mul(2, 3) == 6\n\n\n"
        "def test_add():\n    assert True  # shadows the proving suite test\n"
    )
    res = check_closure(before, "bank.py", "test_bank.py", candidate, target,
                        cwd=str(in_tmp))
    assert res.closed  # the mul target IS closed
    assert add_fn in res.regressions  # but add was collateral damage
    assert not res.legitimate  # so the closure is refused
