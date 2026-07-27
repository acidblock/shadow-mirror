"""Git-diff → changed-line extraction for ``sm plan --diff``.

Consume ``git`` out of process (like ``_run.py`` consumes coverage/pytest); the
package stays dependency-free. The parser is split out as a pure function so the
mapping logic is unit-testable without a repository.
"""

from __future__ import annotations

import re
import subprocess

__all__ = ["changed_lines", "_parse_changed_lines"]

# Unified-diff hunk header: ``@@ -old[,oldn] +new[,newn] @@``. We want the
# *new* side (added/modified lines in the post-change tree). ``newn`` defaults to
# 1 when omitted; ``newn == 0`` is a pure deletion (no new lines) → contributes
# nothing, which is correct: deleted code maps to no current node.
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _parse_changed_lines(diff_text: str) -> set[int]:
    """New-side line numbers touched by a unified diff (``--unified=0``)."""
    lines: set[int] = set()
    for line in diff_text.splitlines():
        m = _HUNK.match(line)
        if m is None:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        lines.update(range(start, start + count))
    return lines


def changed_lines(module_path: str, base: str, cwd: str) -> set[int]:
    """Lines of ``module_path`` changed between ``base`` and the working tree.

    Runs ``git diff --unified=0 <base> -- <module_path>``. Raises ``RuntimeError``
    on git failure (e.g. an unknown ref) so the caller can report it cleanly.
    """
    result = subprocess.run(
        ["git", "diff", "--unified=0", base, "--", module_path],
        cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed for {base!r}: {result.stderr.strip()}")
    return _parse_changed_lines(result.stdout)
