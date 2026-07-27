"""Tests for the aggregation control — each pins exactly ONE of two sites."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import calc  # noqa: E402


def test_combine_product_only():
    # pins the `*` site; the `+` site (lo) is never asserted
    assert calc.combine(3, 4)[0] == 12


def test_halves_positive_only():
    # only the n > 0 branch runs; `return n * 10` is never exercised
    assert calc.halves(4) == 2
