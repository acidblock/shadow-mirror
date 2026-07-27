"""Mechanism tests for ``build_brief`` — the generation brief + acceptance
contract. Pure post-processing over a plan, so these run fast (no subprocess).
"""

from shadow_mirror.brief import ACCEPTANCE, build_brief
from shadow_mirror.map import NA, CoverageMap, LevelVerdict, MapNode
from shadow_mirror.plan import build_plan
from shadow_mirror.resilient import GAP_UNASSERTED, GAP_UNEXERCISED, PROVEN

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


CHARGE = _node("m.py::charge", "charge", 2, [
    ("functional", GAP_UNEXERCISED), ("behavioral", GAP_UNASSERTED),
    ("performant", NA), ("resilient", GAP_UNASSERTED), ("observable", NA)])
TOTAL = _node("m.py::Cart.total", "Cart.total", 1, [
    ("functional", PROVEN), ("behavioral", NA), ("performant", NA),
    ("resilient", GAP_UNASSERTED), ("observable", NA)])


def _brief(**kw):
    return build_brief(build_plan(_cmap(CHARGE, TOTAL), SRC, **kw))


def test_provenance_chain_is_map_then_plan_then_brief():
    cmap = _cmap(CHARGE, TOTAL)
    plan = build_plan(cmap, SRC)
    brief = build_brief(plan)
    assert brief.map_ref == cmap.evidence_ref() == plan.source_evidence_ref
    assert brief.plan_ref == plan.evidence_ref()
    assert brief.evidence_ref() not in (brief.map_ref, brief.plan_ref)


def test_gaps_preserve_plan_ranking():
    plan = build_plan(_cmap(CHARGE, TOTAL), SRC)
    brief = build_brief(plan)
    assert [(g.qualname, g.level) for g in brief.gaps] == \
        [(it.qualname, it.level) for it in plan.items]


def test_each_gap_carries_a_level_obligation():
    brief = _brief()
    by = {(g.qualname, g.level): g for g in brief.gaps}
    assert "return→None" in by[("charge", "functional")].obligation
    assert "operator swap" in by[("charge", "behavioral")].obligation
    assert "raise" in by[("charge", "resilient")].obligation


def test_acceptance_contract_names_the_three_checks():
    brief = _brief()
    assert brief.canonical_dict()["acceptance"] == ACCEPTANCE
    for token in ("VALID", "CLOSED", "REGRESSION"):
        assert token in ACCEPTANCE


def test_prompt_carries_no_fabricated_oracle():
    # every stub keeps a <PLACEHOLDER> or pytest.raises — never a concrete value
    text = _brief().to_prompt()
    assert "ACCEPTANCE" in text and "GAPS" in text
    for g in _brief().gaps:
        assert "<" in g.stub and ">" in g.stub


def test_deterministic_evidence_ref():
    assert _brief().evidence_ref() == _brief().evidence_ref()


def test_diff_base_propagates_into_brief_and_ref():
    full = _brief()
    scoped = _brief(changed_lines={3}, diff_base="HEAD")
    assert scoped.diff_base == "HEAD"
    assert scoped.canonical_dict()["diff_base"] == "HEAD"
    assert "diff_base" not in full.canonical_dict()  # absent → back-compatible ref
    assert scoped.evidence_ref() != full.evidence_ref()


def test_empty_plan_yields_empty_brief():
    clean = _node("m.py::ok", "ok", 1, [("functional", PROVEN), ("behavioral", NA),
                                        ("performant", NA), ("resilient", NA), ("observable", NA)])
    brief = build_brief(build_plan(_cmap(clean), SRC))
    assert brief.gaps == ()
    assert "no gaps" in brief.to_prompt()
