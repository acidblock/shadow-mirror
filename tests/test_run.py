"""Unit tests for the hardened in-place mutation (`_run.mutated_file`).

The crash/concurrency hardening is pure file ops, so these are fast — no pytest
subprocess. The live path (a recovery record written *during* a real mutation run)
is exercised by the full engine suite, which drives `mutated_file` thousands of
times.
"""

import hashlib

import pytest

from shadow_mirror._run import (
    _recovery_path,
    _self_heal,
    _write_recovery,
    mutated_file,
)

ORIG = b"x = 1\n"
MUT = b"x = 2\n"
MUT_SHA = hashlib.sha256(MUT).hexdigest()


def _plant(tmp_path, file_bytes):
    """A target left in `file_bytes` plus a recovery record for ORIG→MUT."""
    f = tmp_path / "m.py"
    f.write_bytes(file_bytes)
    rec = _recovery_path(f)
    _write_recovery(rec, ORIG, MUT_SHA)
    return f, rec


def test_mutated_file_swaps_during_and_restores_after(tmp_path):
    f = tmp_path / "m.py"
    f.write_bytes(ORIG)
    rec = _recovery_path(f)
    with mutated_file(str(f), "x = 2\n"):
        assert f.read_bytes() == MUT  # mutant in place during the context
        assert rec.exists()  # record present while mutated (the invariant)
    assert f.read_bytes() == ORIG  # restored
    assert not rec.exists()  # record cleaned up


def test_self_heal_restores_provable_mutant(tmp_path):
    # file IS the recorded mutant → provably a crashed run → restore the original
    f, rec = _plant(tmp_path, MUT)
    _self_heal(f, rec)
    assert f.read_bytes() == ORIG
    assert not rec.exists()


def test_self_heal_drops_record_when_already_clean(tmp_path):
    # file already == original (run restored, then crashed) → just drop the record
    f, rec = _plant(tmp_path, ORIG)
    _self_heal(f, rec)
    assert f.read_bytes() == ORIG
    assert not rec.exists()


def test_self_heal_refuses_when_user_edited(tmp_path):
    # matches neither original nor the expected mutant → a user edit → refuse,
    # never clobber, and preserve the record (the only copy of the true original)
    edited = b"x = 999  # my work\n"
    f, rec = _plant(tmp_path, edited)
    with pytest.raises(RuntimeError, match="modified after an interrupted run"):
        _self_heal(f, rec)
    assert f.read_bytes() == edited  # untouched
    assert rec.exists()  # original still preserved


def test_self_heal_refuses_on_corrupt_record(tmp_path):
    f = tmp_path / "m.py"
    f.write_bytes(MUT)
    rec = _recovery_path(f)
    rec.write_text("{ not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unreadable recovery record"):
        _self_heal(f, rec)
    assert rec.exists()  # left for manual inspection


def test_mutated_file_self_heals_a_stale_record_first(tmp_path):
    # end-to-end: a prior crash left the file as a mutant + a record; the next
    # mutated_file call heals it BEFORE applying its own mutation, and ends clean
    f, rec = _plant(tmp_path, MUT)
    with mutated_file(str(f), "x = 3\n"):
        assert f.read_bytes() == b"x = 3\n"
    assert f.read_bytes() == ORIG  # healed to the TRUE original, not the leftover MUT
    assert not rec.exists()
