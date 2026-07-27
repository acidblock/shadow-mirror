"""Observable-level SPIKE fixture (tests-only; never shipped).

Four nodes chosen so an emit-assert mutation must DISCRIMINATE, not merely fire:

- record_purchase: emits, and a test asserts the emission (caplog) -> proven
- compute_tax    : emits, but the test asserts only the return     -> gap-unasserted
- escalate       : emits behind a branch no test takes             -> gap-unexercised
- add            : emits nothing                                   -> n/a
"""

import logging

logger = logging.getLogger("observable_demo")


def record_purchase(item, qty):
    logger.info("purchase recorded: %s x%d", item, qty)
    return {"item": item, "qty": qty}


def compute_tax(amount, rate):
    tax = round(amount * rate, 2)
    logger.info("tax computed: %s", tax)  # exercised, but no test observes it
    return tax


def escalate(level):
    if level > 5:
        logger.warning("escalation: level %d", level)  # never exercised
    return level


def add(a, b):
    return a + b  # no emit — Observable does not apply
