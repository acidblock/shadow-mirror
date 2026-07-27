"""Across-site aggregation control (tests-only; never shipped).

Each node has TWO mutation sites of the same level, but the suite pins only
ONE. This is exactly the node the old any-killed pooling mislabeled `proven`
(one site pinned ⇒ whole node proven) and per-site worst-first scores honestly:

- combine: two operators (`*` asserted, `+` not) — `*` swap dies, `+` swap
           survives. any-killed → `behavioral: proven`; worst-first →
           `behavioral: gap-unasserted` (the `+` logic is unpinned).
- halves : two returns (`n // 2` exercised + asserted, `n * 10` never run) —
           any-killed → `functional: proven`; worst-first →
           `functional: gap-unexercised` (the second return never runs).
"""


def combine(a, b):
    hi = a * b  # asserted by the test
    lo = a + b  # NOT asserted — its operator swap survives
    return hi, lo


def halves(n):
    if n > 0:
        return n // 2  # exercised + asserted
    return n * 10  # never exercised by the suite
