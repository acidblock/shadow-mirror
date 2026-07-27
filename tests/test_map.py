"""Four-level map tests: discrimination, the separation decision, receipts.

Spawns coverage/pytest subprocesses; the full map is built once per module.
"""

from pathlib import Path

import pytest

from shadow_mirror import ReceiptV1
from shadow_mirror.map import NA, RUBRIC_VERSION, build_full_map
from shadow_mirror.resilient import GAP_UNASSERTED, GAP_UNEXERCISED, PROVEN

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parent.parent
FIX_MOD = "tests/fixtures/resilient_demo/orders.py"
FIX_TST = "tests/fixtures/resilient_demo/test_orders.py"
OBS_MOD = "tests/fixtures/observable_demo/service.py"
OBS_TST = "tests/fixtures/observable_demo/test_service.py"
AGG_MOD = "tests/fixtures/aggregation_demo/calc.py"
AGG_TST = "tests/fixtures/aggregation_demo/test_calc.py"
STRICT_MOD = "tests/fixtures/resilient_strict_demo/guard.py"
STRICT_TST = "tests/fixtures/resilient_strict_demo/test_guard.py"
EQUIV_MOD = "tests/fixtures/behavioral_equiv_demo/scale.py"
EQUIV_TST = "tests/fixtures/behavioral_equiv_demo/test_scale.py"


@pytest.fixture(scope="module")
def fmap():
    return build_full_map(FIX_MOD, FIX_TST, cwd=str(ROOT))


@pytest.fixture(scope="module")
def omap():
    return build_full_map(OBS_MOD, OBS_TST, cwd=str(ROOT))


@pytest.fixture(scope="module")
def aggmap():
    return build_full_map(AGG_MOD, AGG_TST, cwd=str(ROOT))


@pytest.fixture(scope="module")
def strictmap():
    return build_full_map(STRICT_MOD, STRICT_TST, cwd=str(ROOT))


@pytest.fixture(scope="module")
def equivmap():
    return build_full_map(EQUIV_MOD, EQUIV_TST, cwd=str(ROOT))


def _levels(fmap):
    return {n.qualname: {lv.level: lv.verdict for lv in n.levels} for n in fmap.nodes}


def test_four_level_discrimination(fmap):
    lv = _levels(fmap)
    # functional = is the output observed?
    assert lv["apply_discount"]["functional"] == PROVEN
    assert lv["charge"]["functional"] == GAP_UNEXERCISED  # return line never runs
    # behavioral = is the logic pinned?
    assert lv["apply_discount"]["behavioral"] == GAP_UNASSERTED  # weak >=0 test
    assert lv["charge"]["behavioral"] == PROVEN  # guard comparison pinned
    # resilient (the P2 signal, preserved)
    assert lv["normalize_qty"]["resilient"] == PROVEN  # except recovery pinned (== 0)
    assert lv["apply_discount"]["resilient"] == GAP_UNASSERTED
    assert lv["refund"]["resilient"] == GAP_UNEXERCISED
    assert lv["validate_sku"]["resilient"] == PROVEN  # custom exception type pinned
    # async raise, type pinned via asyncio.run + pytest.raises — the raise-type-swap
    # is killed through the coroutine path exactly as for the sync `charge`. This is
    # the Python ground truth the JS `rejects.toThrow` conformance row anchors to.
    assert lv["charge_async"]["resilient"] == PROVEN


def test_across_site_aggregation_is_worst_first(aggmap):
    # The leniency fix: a node with one pinned site and one unpinned site reads
    # its WEAKEST site, not `proven`. Old any-killed pooling read both `proven`.
    lv = _levels(aggmap)
    assert lv["combine"]["behavioral"] == GAP_UNASSERTED  # the `+` swap survives
    assert lv["halves"]["functional"] == GAP_UNEXERCISED  # 2nd return never runs


def test_behavioral_equivalent_mutant_is_not_excluded(equivmap):
    # The same `* 1` operator is killable, not equivalent: a value-only test
    # leaves the *1→/1 swap unkilled (6 == 6.0), a type-pinning test kills it
    # (int 6 vs float 6.0). Behavioral must NOT exclude it — that would hide the
    # type gap (a false `proven`). So one node reads gap, the other proven.
    lv = _levels(equivmap)
    assert lv["scale_loose"]["behavioral"] == GAP_UNASSERTED
    assert lv["scale_strict"]["behavioral"] == PROVEN


def test_resilient_within_branch_all_must_die(strictmap):
    # Resilient joins the per-site crowd: within a branch, every mutant must die.
    lv = _levels(strictmap)
    # 503 is a significant, unasserted constant → its mutant survives → gap.
    assert lv["http_guard"]["resilient"] == GAP_UNASSERTED
    # message-only raise → strings aren't mutated → only the type-swap, which the
    # `pytest.raises(ValueError)` kills → proven (no equivalent-mutant false gap).
    assert lv["require"]["resilient"] == PROVEN
    # string-only `except` → no const mutant → blank-except fallback fires; the
    # `== "default"` test kills it → proven (recovery pinned by behavior).
    assert lv["lookup"]["resilient"] == PROVEN


def test_observable_discriminates(omap):
    # rubric v2: the emit-assert signal must do more than fire — four verdicts.
    lv = _levels(omap)
    assert lv["record_purchase"]["observable"] == PROVEN  # caplog asserts the emit
    assert lv["compute_tax"]["observable"] == GAP_UNASSERTED  # emit runs, unobserved
    assert lv["escalate"]["observable"] == GAP_UNEXERCISED  # emit line never runs
    assert lv["add"]["observable"] == NA  # no emit — level does not apply


def test_observable_no_false_signal_without_emits(fmap):
    # A module with zero logging emits must read observable n/a everywhere —
    # never a phantom gap.
    assert all(d["observable"] == NA for d in _levels(fmap).values())


def test_map_stamps_rubric_version(omap):
    assert omap.canonical_dict()["rubric_version"] == RUBRIC_VERSION == 2


def test_functional_behavioral_separation_is_real(fmap):
    # The rubric-v1 gate: keep four levels only if functional and behavioral are
    # NOT the same measurement. They must diverge on ≥1 comparable node.
    lv = _levels(fmap)
    comparable = [q for q, d in lv.items() if d["functional"] != NA and d["behavioral"] != NA]
    differ = [q for q in comparable if lv[q]["functional"] != lv[q]["behavioral"]]
    assert comparable and differ, "functional/behavioral never diverge — consolidate the rubric"


def test_behavioral_positive_control_no_false_gap(fmap):
    # A well-tested arithmetic node must read proven (equivalent-mutant guard).
    assert _levels(fmap)["line_total"]["behavioral"] == PROVEN


def test_performant_positive_control(fmap):
    lv = _levels(fmap)
    assert lv["slow_double"]["performant"] == PROVEN  # a covering test asserts a time bound
    assert any(d["performant"] == NA for d in lv.values())  # others n/a, not a false signal


def test_map_paths_are_repo_relative(fmap):
    assert not fmap.module.startswith("/")
    assert all(not n.node_id.startswith("/") and "::" in n.node_id for n in fmap.nodes)


def test_receipt_instrumentation_is_real_provenance(fmap):
    # The receipt is the durable provenance artifact: its instrumentation must be
    # language-correct (not the old hardcoded "coverage.py") and version-stamped.
    instr = fmap.to_receipt(ts="2026-06-01T00:00:00Z").instrumentation
    assert instr[0] == "python"  # the language, first — a JS map would say "javascript"
    assert any(t.startswith("coverage.py@") for t in instr)  # version-stamped tool
    assert f"sm-rubric@v{RUBRIC_VERSION}" in instr  # the methodology version
    # provenance is NOT in evidence_ref — the hash addresses the verdicts only.
    assert "coverage.py" not in fmap.canonical_json()


def test_receipt_reproducible_and_valid(fmap):
    ref = fmap.evidence_ref()
    again = build_full_map(FIX_MOD, FIX_TST, cwd=str(ROOT))
    assert again.evidence_ref() == ref  # byte-for-byte reproducible across runs
    receipt = fmap.to_receipt(ts="2026-06-01T00:00:00Z")
    assert receipt.phase.value == "SM-5"
    assert receipt.evidence_ref == ref
    assert ReceiptV1.from_json(receipt.to_json()) == receipt
