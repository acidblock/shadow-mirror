"""Tests for git-diff → changed-line extraction (`sm plan --diff`).

The hunk parser is pure and tested without a repo; one slow test exercises the
real ``git diff`` path in a throwaway repository.
"""

import subprocess

import pytest

from shadow_mirror._diff import _parse_changed_lines, changed_lines


def test_parse_single_line():
    assert _parse_changed_lines("@@ -1 +1 @@\n-old\n+new\n") == {1}


def test_parse_multi_line_count():
    assert _parse_changed_lines("@@ -10,2 +12,3 @@\n") == {12, 13, 14}


def test_parse_omitted_new_count_defaults_to_one():
    assert _parse_changed_lines("@@ -5 +7 @@\n") == {7}


def test_parse_pure_deletion_contributes_nothing():
    # +4,0 → no new-side lines; deleted code maps to no current node
    assert _parse_changed_lines("@@ -5,2 +4,0 @@\n") == set()


def test_parse_multiple_hunks_ignores_content_and_headers():
    text = (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-a\n+b\n"
        "@@ -10,0 +11,2 @@\n+x\n+y\n"
    )
    assert _parse_changed_lines(text) == {1, 11, 12}


def test_parse_empty_diff():
    assert _parse_changed_lines("") == set()


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


@pytest.mark.slow
def test_changed_lines_against_real_git(tmp_path):
    _git(["init"], tmp_path)
    f = tmp_path / "m.py"
    f.write_text("a = 1\nb = 2\nc = 3\n")
    _git(["add", "m.py"], tmp_path)
    _git(["commit", "-m", "base"], tmp_path)
    f.write_text("a = 1\nb = 22\nc = 3\n")  # modify line 2 only
    assert changed_lines("m.py", "HEAD", str(tmp_path)) == {2}


@pytest.mark.slow
def test_changed_lines_unknown_ref_raises(tmp_path):
    _git(["init"], tmp_path)
    (tmp_path / "m.py").write_text("x = 1\n")
    _git(["add", "m.py"], tmp_path)
    _git(["commit", "-m", "base"], tmp_path)
    with pytest.raises(RuntimeError):
        changed_lines("m.py", "no-such-ref", str(tmp_path))
