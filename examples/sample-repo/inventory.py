"""A tiny inventory/pricing module — the Shadow Mirror demo sample.

Coverage is deliberately uneven so `sm map`, `sm plan`, and `mutmut` each have
something to say:

- ``restock`` is fully pinned by a value-exact test.
- ``apply_markup`` is *called and checked*, but only weakly (the test asserts the
  result is positive, not the exact price) — line-covered and green, yet its
  arithmetic is unproven.
- ``withdraw``'s out-of-stock guard is never exercised — the happy path is pinned,
  the failure path is dark.
"""


def restock(level, incoming):
    return level + incoming


def apply_markup(cost, rate):
    return round(cost * (1 + rate), 2)


def withdraw(level, amount):
    if amount > level:
        raise ValueError("insufficient stock")
    return level - amount
