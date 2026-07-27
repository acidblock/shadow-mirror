"""Executable invariants for the standing constraints (ROADMAP C1-C5).

Only constraints that are testable at the current phase are enforced here;
the rest are recorded in ``docs/constraints.md`` with the phase at which
they become testable. See that file for the full registry.

Enforced now:
- **C4 (Pristine / standalone)** -- no foreign-project references in any
  shipped, user-facing artifact.

The foreign-project denylist is kept **out of the repository** -- listing the
names here would itself reveal the very names C4 hides. The patterns are loaded
at run time from ``$SM_C4_DENYLIST`` or the gitignored ``incoming/c4-denylist.txt``
(``incoming/`` is the project's name-bearing quarantine -- never tracked, never
shipped). Absent both sources the C4 scan **skips**, so a fresh clone does not
error -- *unless* ``SM_REQUIRE_C4`` is set (CI), where a missing list **fails
loud** so the gate can never silently no-op. CI materializes the list from a
repository secret; see ``.github/workflows/ci.yml``. Tool/registry names
(``pytest``, ``coverage.py``, "Claude Code", ...) are never on the list -- they
are the methodology's application surface, not projects it is defined against.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # 3.10 — the declared package floor
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent

# Shipped, user-facing artifacts. The tests/ tree is intentionally excluded:
# this file is the C4 enforcer and is now name-free, but tests in general are
# not part of the shipped package (the wheel ships only shadow_mirror/).
SHIPPED_GLOBS = (
    "README.md",
    "ROADMAP.md",
    "SHADOW_MIRROR_INTERFACE.md",
    "pyproject.toml",
    "docs/**/*.md",
    "plugin/**/*.md",
    "plugin/**/*.json",
    "shadow_mirror/**/*.py",
)

# The foreign-project denylist lives outside the tree (see module docstring).
_DENYLIST_FILE = REPO_ROOT / "incoming" / "c4-denylist.txt"


def _load_denylist() -> list[str]:
    """Foreign-project regex patterns, from ``$SM_C4_DENYLIST`` or the gitignored
    ``incoming/c4-denylist.txt``. The env var is comma- or newline-separated; the
    file is one pattern per line (so a pattern may contain a comma, and ``#``
    comment prose may too). Blank lines and ``#`` comments are ignored. Returns
    ``[]`` when no source is present."""
    env = os.environ.get("SM_C4_DENYLIST")
    if env is not None:
        lines = env.replace(",", "\n").splitlines()
    elif _DENYLIST_FILE.exists():
        lines = _DENYLIST_FILE.read_text(encoding="utf-8").splitlines()
    else:
        return []
    patterns: list[str] = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _shipped_files() -> list[Path]:
    seen: list[Path] = []
    for pattern in SHIPPED_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.append(path)
    return seen


def test_shipped_artifacts_exist():
    # Guard against the globs silently matching nothing (which would make
    # the C4 scan vacuously pass).
    files = _shipped_files()
    assert len(files) >= 8, f"expected several shipped files, found {len(files)}"


def test_c4_no_foreign_project_references():
    """C4: no reference to any other project in shipped tool or docs.

    The denylist is loaded at run time (kept out of the repo). Without it the scan
    skips — unless ``SM_REQUIRE_C4`` is set, where it fails loud (the CI posture).
    """
    patterns = _load_denylist()
    if not patterns:
        missing = ("no C4 denylist — set $SM_C4_DENYLIST or create the gitignored "
                   "incoming/c4-denylist.txt (CI materializes it from a secret)")
        if os.environ.get("SM_REQUIRE_C4"):
            pytest.fail(f"SM_REQUIRE_C4 is set but {missing}")
        pytest.skip(missing)

    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in patterns]
    violations: list[str] = []
    for path in _shipped_files():
        text = path.read_text(encoding="utf-8")
        for raw, rx in compiled:
            for m in rx.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"{rel}:{line_no} matched /{raw}/ -> {m.group(0)!r}")
    assert not violations, "Foreign-project references found (C4 violation):\n" + "\n".join(
        violations
    )


def test_c1_data_model_has_no_runtime_dependencies():
    """C1 (partial): the data-model layer rebuilds nothing and pulls in no
    runtime measurement deps. This is the current-phase slice of C1; the
    full 'consume, don't rebuild' invariant lands with the engine (P2+).
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_deps = data["project"].get("dependencies", [])
    assert runtime_deps == [], f"data model must stay dependency-free, found {runtime_deps}"
