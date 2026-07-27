"""Mechanism tests for ``sm verify`` — the grounded-generation acceptance gate.

Fast paths (hand-built map / report) cover target validation and serialization.
The subprocess paths drive real closures; the centerpiece is
``test_joint_unsafe_collision`` — two candidates each legitimate *alone* but
unsafe *together*, which only the joint gate catches.
"""

import json

import pytest

from shadow_mirror.cli import main
from shadow_mirror.closure import JointClosure
from shadow_mirror.map import NA, PROVEN, CoverageMap, LevelVerdict, MapNode, build_full_map
from shadow_mirror.receipt import ReceiptV1
from shadow_mirror.resilient import GAP_UNASSERTED
from shadow_mirror.verify import Proposal, Verdict, VerificationReport, verify_proposals

_LEVELS = ("functional", "behavioral", "performant", "resilient", "observable")


def _node(qualname, **verdicts):
    levels = tuple(LevelVerdict(lv, verdicts.get(lv, NA), 0, 0) for lv in _LEVELS)
    return MapNode(node_id=f"m.py::{qualname}", qualname=qualname,
                   complexity=1, executed=True, levels=levels)


def _map(*nodes):
    return CoverageMap(module="m.py", covered_lines=1, num_statements=1, nodes=nodes)


# --- fast: target validation rejects before any subprocess ----------------


def test_unknown_target_is_rejected_without_running():
    cmap = _map(_node("charge", functional=GAP_UNASSERTED))
    p = Proposal("m.py::ghost", "functional", "def test_x(): pass")
    report = verify_proposals(cmap, "m.py", "t.py", [p])
    assert report.verdicts[0].accepted is False
    assert report.verdicts[0].reason.startswith("unknown-target")


def test_target_that_is_not_a_gap_is_rejected():
    cmap = _map(_node("charge", functional=PROVEN))
    p = Proposal("m.py::charge", "functional", "def test_x(): pass")
    report = verify_proposals(cmap, "m.py", "t.py", [p])
    assert report.verdicts[0].accepted is False
    assert report.verdicts[0].reason.startswith("not-a-gap")


# --- fast: report shape, serialization, all_clear -------------------------


def _verdict(node, level, accepted, reason=""):
    return Verdict(node, level, "", accepted=accepted, valid=accepted, closed=accepted,
                   regressions=(), reason=reason)


def test_all_clear_requires_every_proposal_and_joint_safety():
    ok = VerificationReport("m.py", "sha256:x", (_verdict("a", "functional", True),), None)
    assert ok.all_clear
    mixed = VerificationReport("m.py", "sha256:x", (
        _verdict("a", "functional", True), _verdict("b", "functional", False, "valid but …")), None)
    assert not mixed.all_clear
    joint_bad = VerificationReport("m.py", "sha256:x",
        (_verdict("a", "functional", True), _verdict("b", "functional", True)),
        JointClosure(2, valid=True, all_closed=False, regressions=(("m.py::c", "functional"),),
                     reason=""))
    assert not joint_bad.all_clear  # accepted individually, unsafe together


def test_report_serializes_deterministically_and_receipt_round_trips():
    report = VerificationReport("m.py", "sha256:x",
        (_verdict("a", "functional", True), _verdict("b", "resilient", False, "valid but …")),
        JointClosure(1, valid=True, all_closed=True, regressions=(), reason=""))
    assert report.evidence_ref() == report.evidence_ref()
    assert report.canonical_dict()["joint"]["safe"] is True
    receipt = report.to_receipt(ts="2026-06-01T00:00:00Z")
    assert receipt.phase.value == "SM-5"
    assert receipt.outcome.value == "inconclusive"  # one rejection ⇒ not all-clear
    assert ReceiptV1.from_json(receipt.to_json()) == receipt


def test_to_text_marks_accept_and_reject():
    report = VerificationReport("m.py", "sha256:x",
        (_verdict("a", "functional", True), _verdict("b", "resilient", False, "valid but …")), None)
    text = report.to_text()
    assert "1/2 proposals accepted" in text and "ACCEPT" in text and "reject" in text


# --- subprocess: real closures in tmp_path --------------------------------


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


_TWO = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
_RUNS = ("import bank\n\n\ndef test_add_runs():\n    bank.add(2, 3)\n\n\n"
         "def test_mul_runs():\n    bank.mul(2, 3)\n")


def _baseline(in_tmp, module=_TWO, suite=_RUNS):
    (in_tmp / "bank.py").write_text(module, encoding="utf-8")
    (in_tmp / "test_bank.py").write_text(suite, encoding="utf-8")
    return build_full_map(str(in_tmp / "bank.py"), "test_bank.py", cwd=str(in_tmp))


def _nid(cmap, qualname):
    return next(n.node_id for n in cmap.nodes if n.qualname == qualname)


@pytest.mark.slow
def test_mixed_proposals_accept_legit_reject_red_and_nonclosing(in_tmp):
    cmap = _baseline(in_tmp)
    add, mul = _nid(cmap, "add"), _nid(cmap, "mul")
    proposals = [
        Proposal(add, "functional", "def test_a():\n    import bank\n    assert bank.add(2, 3) == 5\n",
                 label="legit"),
        Proposal(mul, "functional", "def test_r():\n    import bank\n    assert bank.mul(2, 3) == 99\n",
                 label="red"),
    ]
    report = verify_proposals(cmap, "bank.py", "test_bank.py", proposals, cwd=str(in_tmp))
    by = {v.label: v for v in report.verdicts}
    assert by["legit"].accepted
    assert not by["red"].accepted and by["red"].reason.startswith("suite-not-green")
    assert report.joint is None  # only one accepted ⇒ no joint build
    assert not report.all_clear


@pytest.mark.slow
def test_two_independent_closers_are_jointly_safe(in_tmp):
    cmap = _baseline(in_tmp)
    add, mul = _nid(cmap, "add"), _nid(cmap, "mul")
    proposals = [
        Proposal(add, "functional", "def test_a():\n    import bank\n    assert bank.add(2, 3) == 5\n"),
        Proposal(mul, "functional", "def test_m():\n    import bank\n    assert bank.mul(2, 3) == 6\n"),
    ]
    report = verify_proposals(cmap, "bank.py", "test_bank.py", proposals, cwd=str(in_tmp))
    assert all(v.accepted for v in report.verdicts)
    assert report.joint is not None and report.joint.safe
    assert report.all_clear


@pytest.mark.slow
def test_cli_verify_reads_manifest_and_gates_exit_code(in_tmp, capsys):
    cmap = _baseline(in_tmp)
    add = _nid(cmap, "add")
    (in_tmp / "good.py").write_text(
        "def test_a():\n    import bank\n    assert bank.add(2, 3) == 5\n", encoding="utf-8")
    (in_tmp / "bad.py").write_text(
        "def test_b():\n    import bank\n    assert bank.add(2, 3) == 99\n", encoding="utf-8")
    (in_tmp / "props.json").write_text(json.dumps([
        {"node_id": add, "level": "functional", "candidate": "good.py"},
        {"node_id": add, "level": "functional", "candidate": "bad.py"},
    ]), encoding="utf-8")
    rc = main(["verify", str(in_tmp / "bank.py"), "--tests", "test_bank.py",
               "--proposals", "props.json", "--cwd", str(in_tmp)])
    assert rc == 1  # one rejection ⇒ not all-clear
    assert "1/2 proposals accepted" in capsys.readouterr().out


@pytest.mark.slow
def test_joint_unsafe_collision(in_tmp):
    # CENTERPIECE — each candidate is legitimate ALONE, but candidate B monkeypatches
    # bank.add at import, so jointly A's `assert add(2,3)==5` fails → the combined
    # suite is not green. Per-proposal checks miss it (B is verified without A
    # present); only the joint gate catches it. The analog of the green-gate dual.
    cmap = _baseline(in_tmp)
    add, mul = _nid(cmap, "add"), _nid(cmap, "mul")
    a = "def test_a():\n    import bank\n    assert bank.add(2, 3) == 5\n"
    b = ("import bank\nbank.add = lambda a, b: 0\n\n\n"
         "def test_m():\n    import bank\n    assert bank.mul(2, 3) == 6\n")
    proposals = [Proposal(add, "functional", a, label="A"),
                 Proposal(mul, "functional", b, label="B")]
    report = verify_proposals(cmap, "bank.py", "test_bank.py", proposals, cwd=str(in_tmp))
    assert all(v.accepted for v in report.verdicts)  # each is legitimate in isolation
    assert report.joint is not None
    assert not report.joint.safe  # but together they collide
    assert report.joint.reason.startswith("joint-suite-not-green")
    assert not report.all_clear  # so the set is not certified
