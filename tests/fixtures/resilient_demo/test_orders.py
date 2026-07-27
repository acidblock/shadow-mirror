"""Tests for the resilient demo fixture.

Deliberately uneven: `apply_discount`'s recovery is *exercised* but only
weakly asserted (value-blind), so it is the NS-1 "runs but unproven" case.
The others pin their error behavior.
"""

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import orders  # noqa: E402


def test_normalize_qty_recovers_to_zero():
    assert orders.normalize_qty("not a number") == 0  # pins the recovery value
    assert orders.normalize_qty("7") == 7


def test_apply_discount_runs_but_value_unpinned():
    # Exercises the missing-code recovery, but asserts nothing about the
    # recovered rate — the error path runs, its correctness is unproven.
    result = orders.apply_discount(100.0, {}, "NOPE")
    assert result >= 0


def test_charge_rejects_nonpositive():
    with pytest.raises(ValueError):  # pins the raised type
        orders.charge(0)


def test_charge_async_rejects_nonpositive():
    # asyncio.run drives the coroutine; pytest.raises pins the async-raised type
    # (the promise-form analog of JS `await expect(...).rejects.toThrow(...)`).
    with pytest.raises(ValueError):
        asyncio.run(orders.charge_async(-1))
    assert asyncio.run(orders.charge_async(5)) == 5


def test_refund_happy_path():
    ledger = [50]
    assert orders.refund(50, ledger) == 50  # never triggers the LookupError


def test_validate_sku_rejects_empty():
    with pytest.raises(orders.OrderError):  # pins a CUSTOM (out-of-table) type
        orders.validate_sku("")
    assert orders.validate_sku("ABC") == "ABC"


def test_line_total_exact_value():
    # strong value assertions pin the arithmetic -> functional AND behavioral proven
    assert orders.line_total(10.0, 3, 0.0) == 30.0
    assert orders.line_total(10.0, 2, 0.1) == 22.0  # tax != 0 kills the 1±tax mutant


def test_slow_double_within_time_budget():
    from time import perf_counter

    start = perf_counter()
    assert orders.slow_double(5) == 10
    assert perf_counter() - start < 1.0  # a real time bound -> performant proven
