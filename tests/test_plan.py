"""Mechanical tests for `sm plan` — determinism, ordering, stub shape.

`build_plan` is pure post-processing over a CoverageMap, so these run fast with
an in-memory map (no coverage/pytest subprocess). We test *mechanics* only:
deterministic order, stable tie-breaking, reproducible evidence_ref, correct
stub templates. The ranking's *quality* (are the top items genuinely the ones to
test?) is a judgment validated by dogfooding, not asserted here.
"""

import ast
from pathlib import Path

import pytest

from shadow_mirror import ReceiptV1
from shadow_mirror.cli import main
from shadow_mirror.map import NA, CoverageMap, LevelVerdict, MapNode
from shadow_mirror.plan import build_plan
from shadow_mirror.resilient import GAP_UNASSERTED, GAP_UNEXERCISED, PROVEN

ROOT = Path(__file__).resolve().parent.parent
FIX_MOD = "tests/fixtures/resilient_demo/orders.py"
FIX_TST = "tests/fixtures/resilient_demo/test_orders.py"

SRC = '''
def charge(amount):
    if amount <= 0:
        raise ValueError("bad")
    return amount


class Cart:
    def total(self, items, tax):
        try:
            return sum(items) * (1 + tax)
        except TypeError:
            return 0
'''


def _node(node_id, qualname, cx, levels):
    return MapNode(node_id=node_id, qualname=qualname, complexity=cx, executed=True,
                   levels=tuple(LevelVerdict(lv, v, 0, 0) for lv, v in levels))


def _cmap(*nodes):
    return CoverageMap(module="m.py", covered_lines=1, num_statements=1, nodes=nodes)


# charge: cx 2, three gaps (deficit 3); Cart.total: cx 1, one recovery gap.
CHARGE = _node("m.py::charge", "charge", 2, [
    ("functional", GAP_UNEXERCISED), ("behavioral", GAP_UNASSERTED),
    ("performant", NA), ("resilient", GAP_UNASSERTED), ("observable", NA)])
TOTAL = _node("m.py::Cart.total", "Cart.total", 1, [
    ("functional", PROVEN), ("behavioral", NA), ("performant", NA),
    ("resilient", GAP_UNASSERTED), ("observable", NA)])


@pytest.fixture
def plan():
    return build_plan(_cmap(CHARGE, TOTAL), SRC)


def _order(plan):
    return [(it.qualname, it.level) for it in plan.items]


def test_ranks_complexity_then_deficit_then_verdict(plan):
    # charge (cx 2) before Cart.total (cx 1); within charge, gap-unasserted
    # (behavioral, resilient) before gap-unexercised (functional); same-verdict
    # ties break on level name.
    assert _order(plan) == [
        ("charge", "behavioral"), ("charge", "resilient"),
        ("charge", "functional"), ("Cart.total", "resilient"),
    ]


def test_deficit_and_applicable_counts(plan):
    charge_items = [it for it in plan.items if it.qualname == "charge"]
    assert all(it.deficit == 3 and it.applicable == 3 for it in charge_items)
    total_item = next(it for it in plan.items if it.qualname == "Cart.total")
    assert total_item.deficit == 1 and total_item.applicable == 2


def test_stub_templates(plan):
    stub = {(it.qualname, it.level): it.stub for it in plan.items}
    assert stub[("charge", "functional")] == "assert charge(<amount>) == <EXPECTED>"
    assert "== <EXACT>" in stub[("charge", "behavioral")]
    # a raise-branch → pytest.raises with the real exception type
    assert stub[("charge", "resilient")] == "with pytest.raises(ValueError): charge(<amount>)"
    # an except-recovery branch → assert the recovered value, NOT pytest.raises
    assert stub[("Cart.total", "resilient")].startswith("assert total(<items>, <tax>) == <RECOVERED>")


def test_signature_drops_self_and_is_a_scaffold(plan):
    # method receiver dropped; placeholder names, never callable arguments
    total = next(it for it in plan.items if it.qualname == "Cart.total")
    assert total.signature == "total(<items>, <tax>)"


def test_signature_degrades_when_source_lacks_node():
    node = _node("m.py::ghost", "ghost", 1, [("functional", GAP_UNASSERTED)])
    plan = build_plan(_cmap(node), SRC)  # 'ghost' is not in SRC
    assert plan.items[0].signature == "ghost(...)"


def test_no_fabricated_oracle(plan):
    # every stub leaves a <PLACEHOLDER> or pytest.raises — never a concrete value
    for it in plan.items:
        assert "<" in it.stub and ">" in it.stub


def test_deterministic_and_reproducible(plan):
    again = build_plan(_cmap(TOTAL, CHARGE), SRC)  # input order swapped
    assert _order(plan) == _order(again)  # sort is stable regardless of input order
    assert plan.evidence_ref() == again.evidence_ref()


def test_tie_breaks_on_node_id():
    # identical cx + deficit + verdict → deterministic order by node_id then level
    a = _node("m.py::a", "a", 1, [("functional", GAP_UNASSERTED)])
    b = _node("m.py::b", "b", 1, [("functional", GAP_UNASSERTED)])
    assert _order(build_plan(_cmap(b, a), SRC)) == [("a", "functional"), ("b", "functional")]


def test_to_receipt_is_sm2_inconclusive_and_round_trips(plan):
    receipt = plan.to_receipt(ts="2026-06-01T00:00:00Z")
    assert receipt.phase.value == "SM-2"
    assert receipt.outcome.value == "inconclusive"  # forward-looking: not yet run
    assert receipt.evidence_ref == plan.evidence_ref()
    assert ReceiptV1.from_json(receipt.to_json()) == receipt


def test_empty_plan_when_no_gaps():
    clean = _node("m.py::ok", "ok", 1, [("functional", PROVEN), ("behavioral", NA),
                                        ("performant", NA), ("resilient", NA), ("observable", NA)])
    plan = build_plan(_cmap(clean), SRC)
    assert plan.items == ()
    assert "no gaps" in plan.to_text()
    assert plan.to_receipt(ts="2026-06-01T00:00:00Z").assertion == "no gaps"


def test_diff_scopes_to_changed_nodes():
    # charge spans SRC lines 2-5; a change on line 3 scopes the plan to charge,
    # dropping Cart.total (lines 9-13) entirely.
    plan = build_plan(_cmap(CHARGE, TOTAL), SRC, changed_lines={3}, diff_base="HEAD")
    assert {it.qualname for it in plan.items} == {"charge"}
    assert plan.diff_base == "HEAD"


def test_diff_scope_records_base_and_changes_evidence_ref():
    full = build_plan(_cmap(CHARGE, TOTAL), SRC)
    scoped = build_plan(_cmap(CHARGE, TOTAL), SRC, changed_lines={3}, diff_base="HEAD")
    assert "diff_base" not in full.canonical_dict()  # absent → back-compatible
    assert scoped.canonical_dict()["diff_base"] == "HEAD"
    assert scoped.evidence_ref() != full.evidence_ref()


def test_no_diff_is_byte_identical_to_increment_1():
    # changed_lines=None must produce the same bytes as the no-arg call
    a = build_plan(_cmap(CHARGE, TOTAL), SRC)
    b = build_plan(_cmap(CHARGE, TOTAL), SRC, changed_lines=None, diff_base=None)
    assert a.evidence_ref() == b.evidence_ref()


def test_diff_excludes_unlocatable_node():
    # a node not found in source can't be confidently placed in the diff → excluded
    ghost = _node("m.py::ghost", "ghost", 1, [("functional", GAP_UNASSERTED)])
    plan = build_plan(_cmap(ghost), SRC, changed_lines={3}, diff_base="HEAD")
    assert plan.items == ()


def test_plan_diff_bad_ref_exits_2():
    # the --diff error contract: an unknown ref reports cleanly and exits 2,
    # before any map build (so this is fast).
    assert main(["plan", FIX_MOD, "--tests", FIX_TST, "--cwd", str(ROOT),
                 "--diff", "no-such-ref-xyz"]) == 2


@pytest.mark.slow
def test_cli_brief_flag_emits_acceptance_contract(capsys):
    # --brief reuses the plan path, then emits the generation brief instead.
    assert main(["plan", FIX_MOD, "--tests", FIX_TST, "--cwd", str(ROOT), "--brief"]) == 0
    out = capsys.readouterr().out
    assert "ACCEPTANCE" in out and "obligation:" in out
    capsys.readouterr()  # drain
    assert main(["plan", FIX_MOD, "--tests", FIX_TST, "--cwd", str(ROOT),
                 "--brief", "--json"]) == 0
    assert '"acceptance"' in capsys.readouterr().out  # canonical JSON form


@pytest.mark.slow
def test_end_to_end_plan_from_real_map():
    # integration: real build_full_map → build_plan via the engine, reproducible.
    from shadow_mirror.map import build_full_map

    cmap = build_full_map(FIX_MOD, FIX_TST, cwd=str(ROOT))
    source = (ROOT / FIX_MOD).read_text(encoding="utf-8")
    p1 = build_plan(cmap, source)
    assert p1.items  # the fixture has known gaps
    assert build_plan(cmap, source).evidence_ref() == p1.evidence_ref()
    assert main(["plan", FIX_MOD, "--tests", FIX_TST, "--cwd", str(ROOT), "--json"]) == 0
    # drift guard: real build_functions qualnames must align with plan._signatures.
    # If the two AST walks diverge, every signature silently degrades to `fn(...)`
    # (no param placeholders) and the suite would otherwise stay green.
    assert any(it.signature == "charge(<amount>)" for it in p1.items)
    # scoping guard on a REAL map: a change hitting charge's lines must KEEP charge.
    # A qualname mismatch would make _in_scope drop the node silently — worse than
    # a vague signature, and the drift guard above doesn't cover this path.
    cfn = next(n for n in ast.walk(ast.parse(source))
               if isinstance(n, ast.FunctionDef) and n.name == "charge")
    scoped = build_plan(cmap, source, diff_base="probe",
                        changed_lines=set(range(cfn.lineno, cfn.end_lineno + 1)))
    assert {it.qualname for it in scoped.items} == {"charge"}  # kept + selective
    # CLI --diff happy wiring on a clean tree: empty scope, exit 0
    assert main(["plan", FIX_MOD, "--tests", FIX_TST, "--cwd", str(ROOT), "--diff", "HEAD"]) == 0
