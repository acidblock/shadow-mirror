"""Tests for `sm -v/-vv` runtime logging (the observable mutation process)."""

import logging
from pathlib import Path

import pytest

from shadow_mirror.cli import _configure_logging

ROOT = Path(__file__).resolve().parent.parent
MOD = "tests/fixtures/resilient_demo/orders.py"
TST = "tests/fixtures/resilient_demo/test_orders.py"


def test_silent_by_default():
    lg = logging.getLogger("shadow_mirror")
    before = list(lg.handlers)
    _configure_logging(0)
    assert lg.handlers == before  # verbosity 0 attaches nothing — a library import is silent


def test_verbosity_sets_level_and_handler():
    lg = logging.getLogger("shadow_mirror")
    n = len(lg.handlers)
    try:
        _configure_logging(1)
        assert len(lg.handlers) == n + 1 and lg.level == logging.INFO  # -v
        _configure_logging(2)
        assert lg.level == logging.DEBUG  # -vv
    finally:
        lg.handlers = lg.handlers[:n]
        lg.setLevel(logging.WARNING)


@pytest.mark.slow
def test_verbose_emits_per_node_verdict_rows(caplog):
    from shadow_mirror.map import build_full_map

    with caplog.at_level(logging.INFO, logger="shadow_mirror.map"):
        build_full_map(MOD, TST, cwd=str(ROOT))
    text = caplog.text
    assert "sm map:" in text  # the start line (module + line coverage)
    assert "charge" in text and "func=" in text  # a per-node, per-level verdict row
