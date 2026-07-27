"""EvidenceBundle: the standalone form — a receipt with its canonical map embedded.

Built from a directly-constructed CoverageMap (no coverage/pytest subprocess), so
these are fast unit tests of the integrity link, not an engine run.
"""

import copy
from dataclasses import replace

from shadow_mirror import EvidenceBundle
from shadow_mirror.map import CoverageMap, LevelVerdict, MapNode

TS = "2026-06-04T00:00:00Z"


def _map() -> CoverageMap:
    node = MapNode(
        node_id="m.py::f", qualname="f", complexity=1, executed=True,
        levels=(
            LevelVerdict("functional", "proven", 1, 1),
            LevelVerdict("behavioral", "gap-unasserted", 1, 0),
            LevelVerdict("performant", "n/a", 0, 0),
            LevelVerdict("resilient", "n/a", 0, 0),
            LevelVerdict("observable", "n/a", 0, 0),
        ),
    )
    return CoverageMap(module="m.py", covered_lines=3, num_statements=4, nodes=(node,))


def test_bundle_embeds_the_map_and_verifies():
    m = _map()
    b = m.to_bundle(TS)
    assert b.verified  # the embedded map hashes to the receipt's evidence_ref
    assert b.evidence == m.canonical_dict()  # the actual verdicts are present, not just a hash
    assert b.receipt.evidence_ref == m.evidence_ref()


def test_bundle_round_trip_survives_serialization():
    b = _map().to_bundle(TS)
    again = EvidenceBundle.from_json(b.to_json())
    assert again == b
    assert again.verified  # the integrity link holds across JSON round-trip


def test_tampered_map_fails_verification():
    # Edit a verdict in the embedded map (forge a stronger result) -> the hash no
    # longer matches the receipt's evidence_ref -> caught.
    b = _map().to_bundle(TS)
    forged = copy.deepcopy(dict(b.evidence))
    forged["nodes"][0]["levels"]["behavioral"] = "proven"
    assert not EvidenceBundle(receipt=b.receipt, evidence=forged).verified


def test_tampered_receipt_ref_fails_verification():
    b = _map().to_bundle(TS)
    bad_receipt = replace(b.receipt, evidence_ref="sha256:" + "0" * 64)
    assert not EvidenceBundle(receipt=bad_receipt, evidence=b.evidence).verified


def test_verify_canonicalization_matches_map_evidence_ref():
    # Drift guard: bundle._evidence_hash must canonicalize identically to
    # CoverageMap.evidence_ref. A real bundle verifying is the proof they match.
    assert _map().to_bundle(TS).verified
