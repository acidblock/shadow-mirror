"""Subprocess wrappers — *consume* coverage.py and pytest, never reimplement
them (constraint C1). This module imports only the standard library, so
``shadow_mirror`` keeps zero runtime dependencies; coverage and pytest are
required *tools*, invoked out-of-process.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl  # posix: cross-process advisory locking, released by the OS on death
except ImportError:  # pragma: no cover - non-posix degrades to no cross-process lock
    fcntl = None

__all__ = ["CovData", "run_coverage", "run_coverage_with_contexts", "run_tests",
           "run_selected_tests", "mutated_file"]

# Mutants differ by a single character, so consecutive versions share a file
# size; written within one mtime tick, Python would load a *stale* .pyc from the
# previous mutant. Never write bytecode in engine subprocesses — recompile every
# mutant from its own source.
_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

# Locks live in temp (in-the-moment between live processes; never pollute the
# target dir). Recovery records live *next to the file* (deterministic discovery
# by the next run, survive reboot, and a leftover one in `git status` is a
# feature — it surfaces a crashed run).
_LOCK_DIR = Path(tempfile.gettempdir()) / "shadow_mirror-locks"


def _lock_path(target: Path) -> Path:
    key = hashlib.sha256(str(target.resolve()).encode("utf-8")).hexdigest()[:32]
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    return _LOCK_DIR / f"{key}.lock"


def _recovery_path(target: Path) -> Path:
    return target.with_name(target.name + ".sm-recovery")


@contextmanager
def _file_lock(target: Path):
    """Exclusive cross-process lock around one in-place mutation (posix). flock is
    released by the OS when the holder dies, so a crashed run never wedges the next."""
    if fcntl is None:  # pragma: no cover - non-posix: no cross-process serialization
        yield
        return
    with open(_lock_path(target), "w") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def _write_recovery(rec_path: Path, original: bytes, mutant_sha: str) -> None:
    """Persist {original, expected-mutant-hash} atomically (temp + rename), so a
    crash mid-write leaves either the old record or none — never a half-written one."""
    payload = json.dumps({"original_b64": base64.b64encode(original).decode("ascii"),
                          "mutant_sha256": mutant_sha})
    tmp = rec_path.with_name(f"{rec_path.name}.tmp{os.getpid()}")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, rec_path)


def _self_heal(target: Path, rec_path: Path) -> None:
    """A leftover record means a prior run crashed mid-mutation. Restore the
    original — but only when the file is *provably* that run's mutant. If it matches
    neither the saved original nor the expected mutant, a user edited it: refuse and
    preserve their copy (the record is the only copy of the true original)."""
    if not rec_path.exists():
        return
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        original = base64.b64decode(rec["original_b64"])
        mutant_sha = rec["mutant_sha256"]
    except (ValueError, KeyError) as exc:  # corrupt/half-written → don't guess
        raise RuntimeError(
            f"shadow_mirror: unreadable recovery record {rec_path}; a prior run may "
            f"have left {target} mutated. Inspect and remove it manually.") from exc
    current = target.read_bytes()
    if hashlib.sha256(current).hexdigest() == mutant_sha:
        target.write_bytes(original)  # provably the leftover mutant → safe to restore
        rec_path.unlink()
    elif hashlib.sha256(current).hexdigest() == hashlib.sha256(original).hexdigest():
        rec_path.unlink()  # already clean — just drop the stale record
    else:
        raise RuntimeError(
            f"shadow_mirror: {target} was modified after an interrupted run (it "
            f"matches neither the saved original nor the expected mutant). The "
            f"original is preserved in {rec_path}; resolve it manually before re-running.")


@dataclass(frozen=True)
class CovData:
    executed_lines: frozenset[int]
    covered: int
    num_statements: int


def _match_file(files: dict, module_path: str) -> str:
    want = Path(module_path).resolve()
    for key in files:
        try:
            if Path(key).resolve() == want or Path(key).name == want.name:
                return key
        except OSError:  # pragma: no cover - defensive
            continue
    raise KeyError(f"{module_path} not found in coverage report ({list(files)})")


def run_coverage(module_path: str, tests_path: str, cwd: str) -> CovData:
    """Run the test suite under coverage.py scoped to ``module_path``."""
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, ".coverage")
        report = os.path.join(tmp, "cov.json")
        base = [sys.executable, "-m"]
        subprocess.run(
            [*base, "coverage", "run", f"--data-file={data}", f"--include={module_path}",
             "-m", "pytest", str(tests_path), "-q", "-p", "no:cacheprovider"],
            cwd=cwd, capture_output=True, text=True, env=_ENV,
        )
        subprocess.run(
            [*base, "coverage", "json", f"--data-file={data}", "-o", report],
            cwd=cwd, capture_output=True, text=True, env=_ENV,
        )
        payload = json.loads(Path(report).read_text(encoding="utf-8"))
    files = payload.get("files", {})
    entry = files[_match_file(files, module_path)]
    summary = entry["summary"]
    return CovData(
        executed_lines=frozenset(entry["executed_lines"]),
        covered=summary["covered_lines"],
        num_statements=summary["num_statements"],
    )


def _ctx_to_nodeid(ctx: str, tests_path: str) -> str | None:
    """coverage dynamic_context (``module.func``) -> a runnable pytest nodeid."""
    name = ctx.split("|", 1)[0].split(".")[-1].strip()
    return f"{tests_path}::{name}" if name else None


def run_coverage_with_contexts(
    module_path: str, tests_path: str, cwd: str
) -> tuple[CovData, dict[int, frozenset[str]]]:
    """Like :func:`run_coverage`, plus a per-line set of covering test nodeids."""
    with tempfile.TemporaryDirectory() as tmp:
        data, report = os.path.join(tmp, ".coverage"), os.path.join(tmp, "cov.json")
        rc = os.path.join(tmp, "rc")
        Path(rc).write_text("[run]\ndynamic_context = test_function\n", encoding="utf-8")
        base = [sys.executable, "-m"]
        subprocess.run(
            [*base, "coverage", "run", f"--rcfile={rc}", f"--data-file={data}",
             f"--include={module_path}", "-m", "pytest", str(tests_path), "-q",
             "-p", "no:cacheprovider"],
            cwd=cwd, capture_output=True, text=True, env=_ENV,
        )
        subprocess.run(
            [*base, "coverage", "json", f"--data-file={data}", "-o", report, "--show-contexts"],
            cwd=cwd, capture_output=True, text=True, env=_ENV,
        )
        payload = json.loads(Path(report).read_text(encoding="utf-8"))
    files = payload.get("files", {})
    entry = files[_match_file(files, module_path)]
    summary = entry["summary"]
    line_tests: dict[int, frozenset[str]] = {}
    for line_str, contexts in entry.get("contexts", {}).items():
        ids = {nid for c in contexts if (nid := _ctx_to_nodeid(c, tests_path))}
        if ids:
            line_tests[int(line_str)] = frozenset(ids)
    cov = CovData(
        executed_lines=frozenset(entry["executed_lines"]),
        covered=summary["covered_lines"],
        num_statements=summary["num_statements"],
    )
    return cov, line_tests


def run_tests(tests_path: str, cwd: str) -> int:
    """Return the pytest exit code (0 == all passed)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_path), "-q", "-p", "no:cacheprovider"],
        cwd=cwd, capture_output=True, text=True, env=_ENV,
    )
    return result.returncode


def run_selected_tests(nodeids: list[str], cwd: str) -> int:
    """Run exactly ``nodeids``; return the pytest exit code."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *nodeids, "-q", "-p", "no:cacheprovider"],
        cwd=cwd, capture_output=True, text=True, env=_ENV,
    )
    return result.returncode


@contextmanager
def mutated_file(path: str, new_source: str):
    """Temporarily replace ``path`` with ``new_source``; always restore.

    Hardened against the two failure modes dogfooding on a real source tree
    surfaced — because this mutates the user's *actual* file in place:

    1. **Concurrency** — two engine runs racing on the same file would corrupt it
       (one's restore clobbers the other's). A cross-process ``flock`` serializes
       them (posix; a no-op elsewhere, where you simply must not run two at once).
    2. **Hard crash** — a SIGKILL skips ``finally`` and leaves the file mutated. A
       recovery sidecar (written *before* the mutant, holding the original bytes +
       the expected mutant hash) lets the next run restore it — but only when the
       file is provably that mutant, never clobbering an intervening user edit.

    Invariant: under the lock the file is always either the original (record
    optional) or the mutant (record present) — never mutated without a record.
    """
    target = Path(path)
    rec_path = _recovery_path(target)
    mutant_bytes = new_source.encode("utf-8")
    with _file_lock(target):
        _self_heal(target, rec_path)  # after lock, before reading the (true) original
        original = target.read_bytes()
        _write_recovery(rec_path, original, hashlib.sha256(mutant_bytes).hexdigest())
        try:
            target.write_bytes(mutant_bytes)
            yield
        finally:
            target.write_bytes(original)
            if target.read_bytes() != original:  # verified restore — fail loud, keep record
                raise RuntimeError(
                    f"shadow_mirror: failed to restore {target} to its original bytes; "
                    f"the original is preserved in {rec_path}.")
            rec_path.unlink(missing_ok=True)
