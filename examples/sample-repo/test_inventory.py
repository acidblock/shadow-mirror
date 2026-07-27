"""Tests for the demo sample — intentionally uneven (see inventory.py)."""

import inventory


def test_restock_adds_units():
    assert inventory.restock(10, 5) == 15  # exact value → pins the '+'


def test_apply_markup_returns_a_price():
    # Weak on purpose: checks only that *a positive number* came back, not the
    # exact arithmetic. Line-covered and green — but the operators aren't pinned.
    assert inventory.apply_markup(100, 0.10) > 0


def test_withdraw_reduces_stock():
    assert inventory.withdraw(10, 3) == 7  # happy path pinned …
    # … but nothing ever calls withdraw with amount > level, so the raise is dark.
