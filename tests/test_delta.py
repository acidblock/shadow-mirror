"""Mechanism tests for ``sm delta`` — map comparison + the PR gate. Pure dict
comparison, so these are fast (no subprocess)."""

import json

from shadow_mirror.cli import main
from shadow_mirror.delta import build_delta
from shadow_mirror.map import (
    NA,
    PROVEN,
    CoverageMap,
    LevelVerdict,
    MapNode,
)
from shadow_mirror.receipt import ReceiptV1
from shadow_mirror.resilient import GAP_UNASSERTED, GAP_UNEXERCISED

_LEVELS = ("functional", "behavioral", "performant", "resilient", "observable")


def _map_dict(*nodes):
    return {"rubric_version": 2, "module": "m.py",
            "line_coverage": {"covered_lines": 1, "num_statements": 1},
            "nodes": list(nodes)}


def _nd(node_id, cx, **levels):
    full = {lv: levels.get(lv, NA) for lv in _LEVELS}
    return {"node_id": node_id, "complexity": cx, "executed": True, "levels": full}


# charge: functional gap→proven (closed), behavioral proven→gap (regressed),
# resilient proven→proven (unchanged). newfn: a new cx-5 node with a gap.
BASE = _map_dict(
    _nd("m.py::charge", 2, functional=GAP_UNEXERCISED, behavioral=PROVEN, resilient=PROVEN))
HEAD = _map_dict(
    _nd("m.py::charge", 2, functional=PROVEN, behavioral=GAP_UNASSERTED, resilient=PROVEN),
    _nd("m.py::newfn", 5, functional=GAP_UNASSERTED))


def test_classifies_closed_regressed_and_new_gaps():
    d = build_delta(BASE, HEAD)
    assert [(c.qualname, c.level) for c in d.closed] == [("charge", "functional")]
    assert [(c.qualname, c.level) for c in d.regressed] == [("charge", "behavioral")]
    assert [(c.qualname, c.level) for c in d.new_gaps] == [("newfn", "functional")]


def test_gate_set_thresholds_new_gaps_on_complexity_but_always_regressions():
    d = build_delta(BASE, HEAD)
    at5 = d.high_complexity_new_or_regressed(5)  # regressed + newfn (cx5 >= 5)
    assert {(c.qualname, c.level) for c in at5} == {("charge", "behavioral"), ("newfn", "functional")}
    at6 = d.high_complexity_new_or_regressed(6)  # newfn (cx5) drops out; regression stays
    assert {(c.qualname, c.level) for c in at6} == {("charge", "behavioral")}


def test_new_gap_on_existing_node_is_flagged_and_gates():
    # The canonical gate case: a PR adds an untested raise/except to an existing
    # complex function → that level goes n/a → gap on a node that already existed.
    # It must be flagged (and trip --gate-complexity), not fall through.
    base = _map_dict(_nd("m.py::foo", 8, functional=PROVEN))  # resilient n/a
    head = _map_dict(_nd("m.py::foo", 9, functional=PROVEN, resilient=GAP_UNEXERCISED))
    d = build_delta(base, head)
    assert [(c.qualname, c.level) for c in d.new_gaps] == [("foo", "resilient")]
    assert d.new_gaps[0].base_verdict == NA  # existing node (n/a), not None (new node)
    assert d.high_complexity_new_or_regressed(8)  # cx-9 node ≥ 8 → gate trips
    assert not d.closed and not d.regressed


def test_gap_to_gap_and_gap_to_na_are_not_flagged():
    # A cell that was already a gap (still open, or dropped to n/a) is not a *new*
    # loss — neither closed, regressed, nor a new gap.
    base = _map_dict(_nd("m.py::f", 1, functional=GAP_UNASSERTED, behavioral=GAP_UNASSERTED))
    head = _map_dict(_nd("m.py::f", 1, functional=GAP_UNEXERCISED, behavioral=NA))
    d = build_delta(base, head)
    assert not (d.closed or d.regressed or d.new_gaps)


def test_no_change_yields_empty_delta():
    d = build_delta(BASE, BASE)
    assert not (d.closed or d.regressed or d.new_gaps)
    assert "no semantic-coverage change" in d.to_text()


def test_provenance_refs_match_source_maps_and_are_deterministic():
    # build_delta accepts CoverageMap objects; the recorded refs equal the maps'
    # own evidence_refs (provenance), and the delta ref is reproducible.
    def _cm(*nodes):
        return CoverageMap(module="m.py", covered_lines=1, num_statements=1, nodes=nodes)

    def _node(node_id, **lv):
        levels = tuple(LevelVerdict(k, lv.get(k, NA), 0, 0) for k in _LEVELS)
        return MapNode(node_id=node_id, qualname=node_id.split("::")[-1],
                       complexity=1, executed=True, levels=levels)

    base = _cm(_node("m.py::f", functional=GAP_UNEXERCISED))
    head = _cm(_node("m.py::f", functional=PROVEN))
    d = build_delta(base, head)
    assert d.base_ref == base.evidence_ref()
    assert d.head_ref == head.evidence_ref()
    assert build_delta(base, head).evidence_ref() == d.evidence_ref()
    assert [(c.qualname, c.level) for c in d.closed] == [("f", "functional")]


def test_receipt_is_falsified_on_regression_else_verified_and_round_trips():
    reg = build_delta(BASE, HEAD).to_receipt(ts="2026-06-02T00:00:00Z")
    assert reg.outcome.value == "falsified"  # a regression falsifies "no loss"
    assert ReceiptV1.from_json(reg.to_json()) == reg
    clean = build_delta(BASE, BASE).to_receipt(ts="2026-06-02T00:00:00Z")
    assert clean.outcome.value == "verified"


def test_to_text_blocks():
    text = build_delta(BASE, HEAD).to_text()
    assert "closed" in text and "regressed" in text and "new gaps" in text
    assert "charge/behavioral" in text and "newfn/functional" in text


def test_markdown_has_sticky_marker_counts_and_orders_regressions_first():
    md = build_delta(BASE, HEAD).to_markdown()
    assert md.startswith("<!-- shadow-mirror-delta -->")  # sticky find-and-update marker
    assert "1 closed · 1 regressed · 1 new gap(s)" in md
    assert "`charge/behavioral`" in md and "`newfn/functional`" in md
    assert "_(new node)_" in md  # new-node base label
    # regressions must appear before closed (what a reviewer must see first)
    assert md.index("Regressed") < md.index("Closed")


def test_markdown_no_change_is_explicit():
    md = build_delta(BASE, BASE).to_markdown()
    assert md.startswith("<!-- shadow-mirror-delta -->")
    assert "No semantic-coverage change" in md


def test_cli_delta_markdown(tmp_path, capsys):
    base, head = _write_maps(tmp_path)
    assert main(["delta", base, head, "--markdown"]) == 0
    assert "<!-- shadow-mirror-delta -->" in capsys.readouterr().out


# --- CLI gate exit codes --------------------------------------------------


def _write_maps(tmp_path):
    (tmp_path / "base.json").write_text(json.dumps(BASE), encoding="utf-8")
    (tmp_path / "head.json").write_text(json.dumps(HEAD), encoding="utf-8")
    return str(tmp_path / "base.json"), str(tmp_path / "head.json")


def test_cli_delta_default_exit_zero(tmp_path, capsys):
    base, head = _write_maps(tmp_path)
    assert main(["delta", base, head]) == 0  # gate off by default (C3)
    assert "regressed 1" in capsys.readouterr().out


def test_cli_fail_on_regression_exits_1(tmp_path):
    base, head = _write_maps(tmp_path)
    assert main(["delta", base, head, "--fail-on-regression"]) == 1


def test_cli_gate_complexity(tmp_path):
    base, head = _write_maps(tmp_path)
    # newfn (cx5) is a new gap; threshold 5 trips, threshold 6 does not (but the
    # regression alone would only trip via --fail-on-regression, not this flag)
    assert main(["delta", base, head, "--gate-complexity", "5"]) == 1
    # at threshold 99 no new gap qualifies AND --fail-on-regression not set, but the
    # gate-complexity set still includes regressions → exit 1
    assert main(["delta", base, head, "--gate-complexity", "99"]) == 1


def test_cli_gate_complexity_clean_when_no_regression_and_high_threshold(tmp_path):
    # base→base: no regression, no new gap → gate passes at any threshold
    (tmp_path / "b.json").write_text(json.dumps(BASE), encoding="utf-8")
    assert main(["delta", str(tmp_path / "b.json"), str(tmp_path / "b.json"),
                 "--gate-complexity", "1"]) == 0
