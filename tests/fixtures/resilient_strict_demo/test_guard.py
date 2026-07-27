"""Both tests pin the raised TYPE only — never the status code or message."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import guard  # noqa: E402


def test_http_guard_raises_type_only():
    with pytest.raises(guard.HttpError):  # pins the type, not the 503
        guard.http_guard(500)


def test_require_raises_type_only():
    with pytest.raises(ValueError):  # pins the type; the message is incidental
        guard.require("")


def test_lookup_recovers_to_default():
    assert guard.lookup({}, "missing") == "default"  # pins the recovery by value
