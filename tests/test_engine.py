"""End-to-end engine tests: resilient signal discrimination + C2 parity.

These spawn coverage.py/pytest subprocesses (the engine consumes them out of
process), so they are slower than the data-model tests. Each ``build_map`` is
shared module-wide.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from shadow_mirror.resilient import GAP_UNASSERTED, GAP_UNEXERCISED, PROVEN, build_map

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parent.parent
FIX_MOD = "tests/fixtures/resilient_demo/orders.py"
FIX_TST = "tests/fixtures/resilient_demo/test_orders.py"
RCPT_MOD = "shadow_mirror/receipt.py"
RCPT_TST = "tests/test_receipt.py"
STRICT_MOD = "tests/fixtures/resilient_strict_demo/guard.py"
STRICT_TST = "tests/fixtures/resilient_strict_demo/test_guard.py"

# Snapshot at import — before any fixture mutates a file — so the restore check
# compares against the true pre-run bytes, independent of git working-tree state.
_BEFORE = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (RCPT_MOD, FIX_MOD)}


@pytest.fixture(scope="module")
def fixture_map():
    return build_map(FIX_MOD, FIX_TST, cwd=str(ROOT))


@pytest.fixture(scope="module")
def receipt_map():
    return build_map(RCPT_MOD, RCPT_TST, cwd=str(ROOT))


@pytest.fixture(scope="module")
def strict_map():
    return build_map(STRICT_MOD, STRICT_TST, cwd=str(ROOT))


def test_resilient_all_must_die_and_message_exclusion(strict_map):
    # P2 path mirrors the map path: within-branch all-must-die, strings excluded.
    v = {b.qualname: b.verdict for b in strict_map.branches}
    assert v["http_guard"] == GAP_UNASSERTED  # 503 survives unasserted → gap
    assert v["require"] == PROVEN  # message-only → type-swap pins, no false gap
    assert v["lookup"] == PROVEN  # string-only except → blank-except fallback pins it


def test_resilient_signal_discriminates(fixture_map):
    # Two structurally identical except handlers, opposite verdicts — the
    # signal must do more than fire. This is the positive control.
    verdict = {b.qualname: b.verdict for b in fixture_map.branches}
    assert verdict["normalize_qty"] == PROVEN  # recovery value pinned
    assert verdict["apply_discount"] == GAP_UNASSERTED  # NS-1: runs, unproven
    assert verdict["charge"] == PROVEN  # builtin raised type pinned
    assert verdict["refund"] == GAP_UNEXERCISED  # never exercised
    assert verdict["validate_sku"] == PROVEN  # CUSTOM (out-of-table) type pinned


def test_surfaces_an_ns1_gap(fixture_map):
    # P2 success criterion: ≥1 error path coverage calls covered, no test proves.
    ns1 = [b for b in fixture_map.gaps if b.verdict == GAP_UNASSERTED]
    assert ns1 and ns1[0].executed


def test_no_false_positive_on_well_tested_real_code(receipt_map):
    verdicts = [b.verdict for b in receipt_map.branches]
    assert PROVEN in verdicts  # the tested guard
    assert GAP_UNASSERTED not in verdicts  # no false "runs-but-unproven"
    assert GAP_UNEXERCISED in verdicts  # the genuinely unexercised raise (P1 line 79)


def test_engine_restores_mutated_files(fixture_map, receipt_map):
    # The engine mutates in place; depending on both maps guarantees both
    # build_map runs have completed. Bytes must match the pre-run snapshot.
    after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (RCPT_MOD, FIX_MOD)}
    assert after == _BEFORE


def _coverage_counts(module: str, tests: str) -> tuple[int, int]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        data, report = os.path.join(tmp, ".coverage"), os.path.join(tmp, "c.json")
        subprocess.run(
            [sys.executable, "-m", "coverage", "run", f"--data-file={data}",
             f"--include={module}", "-m", "pytest", tests, "-q", "-p", "no:cacheprovider"],
            cwd=ROOT, capture_output=True, env=env,
        )
        subprocess.run(
            [sys.executable, "-m", "coverage", "json", f"--data-file={data}", "-o", report],
            cwd=ROOT, capture_output=True, env=env,
        )
        payload = json.loads(Path(report).read_text())
    entry = next(v for k, v in payload["files"].items() if k.endswith("receipt.py"))
    return entry["summary"]["covered_lines"], entry["summary"]["num_statements"]


def test_c2_line_parity_exact_integer(receipt_map):
    covered, num_statements = _coverage_counts(RCPT_MOD, RCPT_TST)
    assert receipt_map.covered_lines == covered  # C2: exact integer parity
    assert receipt_map.num_statements == num_statements
