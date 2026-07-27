"""Resilient-level demonstration fixture (tests-only; never shipped).

Four error branches chosen so `sm map` must DISCRIMINATE, not merely fire:

- normalize_qty : except recovers to 0, and a test pins it      -> proven
- apply_discount: except recovers to 0.0, test is value-blind   -> gap-unasserted (NS-1)
- charge        : raise ValueError, a test pins the type        -> proven
- charge_async  : async raise, type pinned via the promise form -> proven
- refund        : raise LookupError, no test triggers it        -> gap-unexercised
- line_total    : arithmetic, a strong value test               -> functional + behavioral proven
- slow_double   : a test asserts a time bound                   -> performant proven
"""

import time


def normalize_qty(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def apply_discount(price, code_table, code):
    try:
        rate = code_table[code]
    except KeyError:
        rate = 0.0
    return round(price * (1 - rate), 2)


def charge(amount):
    if amount <= 0:
        raise ValueError("amount must be positive")
    return amount


async def charge_async(amount):
    # Async mirror of `charge`: an async raise asserted via the promise form
    # (JS `rejects.toThrow`) or `asyncio.run` + `pytest.raises` is the SAME
    # resilient signal — the raise-type-swap is killed by the type-pin -> proven.
    if amount <= 0:
        raise ValueError("amount must be positive")
    return amount


def refund(amount, ledger):
    if amount not in ledger:
        raise LookupError("no such charge")
    ledger.remove(amount)
    return amount


class OrderError(Exception):
    """A custom, out-of-any-table exception type."""


def validate_sku(sku):
    if not sku:
        raise OrderError("empty sku")  # custom type, type pinned by a test -> proven
    return sku


def line_total(unit_price, qty, tax_rate):
    subtotal = unit_price * qty
    return round(subtotal * (1 + tax_rate), 2)


def slow_double(x):
    time.sleep(0.001)
    return x * 2
