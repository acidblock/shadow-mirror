"""Tests for the observable-demo spike fixture.

Deliberately uneven: ``record_purchase``'s emission is asserted (via caplog),
``compute_tax``'s is merely exercised, ``escalate``'s is never reached.
"""

import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import service  # noqa: E402


def test_record_purchase_logs(caplog):
    caplog.set_level(logging.INFO)
    result = service.record_purchase("widget", 3)
    assert result == {"item": "widget", "qty": 3}
    assert "purchase recorded: widget x3" in caplog.text  # observes the emit -> proven


def test_compute_tax_value():
    # exercises the log line, but asserts only the return value
    assert service.compute_tax(100.0, 0.2) == 20.0  # emit unobserved -> gap-unasserted


def test_escalate_passthrough():
    assert service.escalate(1) == 1  # warning branch never taken -> gap-unexercised


def test_add_value():
    assert service.add(2, 3) == 5  # no emit -> n/a
