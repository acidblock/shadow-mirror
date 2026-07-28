"""Unit tests for the hardened in-place mutation (`_run.mutated_file`).

The crash/concurrency hardening is pure file ops, so these are fast — no pytest
subprocess. The live path (a recovery record written *during* a real mutation run)
is exercised by the full engine suite, which drives `mutated_file` thousands of
times.
"""

import hashlib
import os
import signal
import subprocess
import sys
import textwrap
import threading

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


# --- termination unwinds the in-flight mutation (SIGTERM / SIGINT / atexit) ----
#
# `finally` covers KeyboardInterrupt and the sidecar covers SIGKILL via *next-run*
# self-heal; the gap is termination that skips `finally` when there may never be a
# next run — a harness timeout's SIGTERM, a killed CI step. These prove the file
# is restored in THIS process, before death.

_HOLD_SCRIPT = textwrap.dedent(
    """\
    import sys, time
    from shadow_mirror._run import mutated_file

    with mutated_file(sys.argv[1], "x = 2\\n"):
        print("READY", flush=True)
        time.sleep(30)
    """
)


def _hold_mutation(tmp_path, target):
    """A child process parked inside the mutation window, mutant on disk."""
    script = tmp_path / "hold.py"
    script.write_text(_HOLD_SCRIPT, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script), str(target)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert proc.stdout.readline().strip() == "READY"
    assert target.read_bytes() == MUT  # mutant really is on disk mid-window
    return proc


@pytest.mark.skipif(os.name != "posix", reason="signal-death semantics are posix")
def test_sigterm_mid_mutation_restores_before_death(tmp_path):
    f = tmp_path / "m.py"
    f.write_bytes(ORIG)
    proc = _hold_mutation(tmp_path, f)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=10)
    assert proc.returncode == -signal.SIGTERM  # still dies OF SIGTERM (chained default)
    assert f.read_bytes() == ORIG  # restored before death, not left for a next run
    assert not _recovery_path(f).exists()


@pytest.mark.skipif(os.name != "posix", reason="signal-death semantics are posix")
def test_sigint_mid_mutation_restores_before_death(tmp_path):
    f = tmp_path / "m.py"
    f.write_bytes(ORIG)
    proc = _hold_mutation(tmp_path, f)
    proc.send_signal(signal.SIGINT)  # chains to the default KeyboardInterrupt path
    proc.wait(timeout=10)
    assert proc.returncode != 0
    assert f.read_bytes() == ORIG
    assert not _recovery_path(f).exists()


def test_signal_handlers_are_scoped_to_the_mutation_window(tmp_path):
    # The engine must never permanently own the host's signal disposition (the MCP
    # server / library embedders keep theirs): installed inside, restored after.
    f = tmp_path / "m.py"
    f.write_bytes(ORIG)
    before = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
    with mutated_file(str(f), "x = 2\n"):
        during = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
        assert during != before
    after = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
    assert after == before


def test_emergency_restore_races_cleanly_with_normal_exit(tmp_path):
    # A signal at the very end of the window: the handler restores first, then the
    # normal `finally` runs. The double-unwind must be a clean no-op, not an error.
    from shadow_mirror._run import _restore_active

    f = tmp_path / "m.py"
    f.write_bytes(ORIG)
    with mutated_file(str(f), "x = 2\n"):
        _restore_active()  # simulate the handler having already fired
        assert f.read_bytes() == ORIG
    assert f.read_bytes() == ORIG
    assert not _recovery_path(f).exists()


def test_mutation_in_worker_thread_still_restores(tmp_path):
    # signal.signal is main-thread-only; off the main thread the guard must
    # degrade gracefully (atexit + sidecar remain), never error.
    f = tmp_path / "m.py"
    f.write_bytes(ORIG)
    failures = []

    def work():
        try:
            with mutated_file(str(f), "x = 2\n"):
                assert f.read_bytes() == MUT
        except BaseException as exc:  # noqa: BLE001 - surfaced to the main thread
            failures.append(exc)

    t = threading.Thread(target=work)
    t.start()
    t.join(timeout=10)
    assert not failures
    assert f.read_bytes() == ORIG
    assert not _recovery_path(f).exists()
