"""Minimal operation tree — functions and their error branches (P2 slice).

Extracts, from a Python source file, the error-handling branches (`raise`
statements and `except` handlers) that the resilient level scores. Each
branch gets a stable, content-addressable identity (R1):

    <path>::<qualname>#<kind>:<ordinal>

- ``qualname`` is the dotted enclosing function/class path.
- ``ordinal`` is the Nth branch of that ``kind`` in source order within the
  qualname — stable under reformatting and line shifts (not under
  reordering, which is a real structural change; full rename-tolerance is a
  later phase, seeded here by ``shape_hash``).
- ``shape_hash`` is sha256 of the branch's normalized AST (no line numbers).
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ErrorBranch", "FunctionNode", "ModuleTree", "build_tree", "build_functions"]


@dataclass(frozen=True)
class ErrorBranch:
    """One error-handling branch: a ``raise`` or an ``except`` handler."""

    node_id: str
    kind: str  # "raise" | "except"
    qualname: str
    exc_type: str | None  # raised/caught type name, if a simple name
    lineno: int  # first line of the construct
    end_lineno: int
    body_lines: tuple[int, int]  # (start, end) lines to neutralize when mutating
    shape_hash: str


@dataclass(frozen=True)
class FunctionNode:
    """A function/method — the unit of the semantic-coverage map."""

    node_id: str  # <path>::<qualname>
    qualname: str
    lineno: int
    end_lineno: int
    complexity: int  # McCabe-style: 1 + decision points
    return_lines: tuple[int, ...]  # lines of `return <value>` statements (functional)
    has_error_branches: bool
    shape_hash: str


@dataclass(frozen=True)
class ModuleTree:
    path: str
    branches: tuple[ErrorBranch, ...]


_DECISION = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert)


def _owned(fn: ast.AST):
    """Yield nodes inside ``fn``'s own body, not descending into nested scopes."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, nested):
            stack.extend(ast.iter_child_nodes(node))


def _complexity(fn: ast.AST) -> int:
    score = 1
    for node in _owned(fn):
        if isinstance(node, _DECISION):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case):
            score += 1
    return score


def _return_lines(fn: ast.AST) -> tuple[int, ...]:
    return tuple(
        node.lineno
        for node in _owned(fn)
        if isinstance(node, ast.Return)
        and node.value is not None
        and not (isinstance(node.value, ast.Constant) and node.value.value is None)
    )


def build_functions(path: str | Path, source: str | None = None) -> tuple[FunctionNode, ...]:
    """Return every function/method in ``path`` as a :class:`FunctionNode`.

    ``source`` parses the given text (the SPI ``discover`` path — the caller
    already holds the source); when ``None`` the file is read. ``path`` still
    backs ``node_id`` and the parse ``filename`` either way."""
    path = Path(path)
    text = source if source is not None else path.read_text(encoding="utf-8")
    module = ast.parse(text, filename=str(path))
    error_lines = {b.lineno for b in build_tree(path, source).branches}
    out: list[FunctionNode] = []

    def visit(node: ast.AST, qual: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = ".".join(qual + [child.name])
                end = child.end_lineno or child.lineno
                out.append(
                    FunctionNode(
                        node_id=f"{path}::{name}",
                        qualname=name,
                        lineno=child.lineno,
                        end_lineno=end,
                        complexity=_complexity(child),
                        return_lines=_return_lines(child),
                        has_error_branches=any(child.lineno <= ln <= end for ln in error_lines),
                        shape_hash=_shape_hash(child),
                    )
                )
                visit(child, qual + [child.name])
            elif isinstance(child, ast.ClassDef):
                visit(child, qual + [child.name])
            else:
                visit(child, qual)

    visit(module, [])
    return tuple(out)


def _exc_name(node: ast.expr | None) -> str | None:
    """Best-effort simple name of a raised/caught exception expression."""
    if node is None:
        return None
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _shape_hash(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node).encode("utf-8")).hexdigest()[:16]


def _collect(node: ast.AST, qual: list[str], counters: dict, out: list, path: str) -> None:
    """Pre-order walk; ``raise``/``except`` are attributed to the enclosing qualname."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _collect(child, qual + [child.name], counters, out, path)
            continue

        kind = None
        body: list[ast.stmt] = []
        exc: ast.expr | None = None
        if isinstance(child, ast.Raise):
            kind, body, exc = "raise", [child], child.exc
        elif isinstance(child, ast.ExceptHandler):
            kind, body, exc = "except", child.body, child.type  # type: ignore[assignment]

        if kind is not None:
            qualname = ".".join(qual) or "<module>"
            key = (qualname, kind)
            ordinal = counters.get(key, 0)
            counters[key] = ordinal + 1
            out.append(
                ErrorBranch(
                    node_id=f"{path}::{qualname}#{kind}:{ordinal}",
                    kind=kind,
                    qualname=qualname,
                    exc_type=_exc_name(exc),
                    lineno=child.lineno,
                    end_lineno=child.end_lineno or child.lineno,
                    body_lines=(body[0].lineno, body[-1].end_lineno or body[-1].lineno),
                    shape_hash=_shape_hash(child),
                )
            )
        _collect(child, qual, counters, out, path)


def build_tree(path: str | Path, source: str | None = None) -> ModuleTree:
    """Parse ``path`` (or ``source`` if given) and return its error-branch tree."""
    path = Path(path)
    text = source if source is not None else path.read_text(encoding="utf-8")
    module = ast.parse(text, filename=str(path))
    branches: list[ErrorBranch] = []
    _collect(module, [], {}, branches, str(path))
    return ModuleTree(path=str(path), branches=tuple(branches))
