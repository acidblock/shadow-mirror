"""MCP tool *handlers* — plain functions that return JSON-able dicts.

This module imports only existing ``shadow_mirror`` modules — **never ``mcp``** —
so the package stays dependency-free (C1) and the handlers are testable without the
SDK installed. :mod:`shadow_mirror.mcp_server` is the thin wiring that registers
these with the MCP runtime.

**cwd anchoring.** The engine resolves and mutates the target *relative to the
process cwd* (see :func:`shadow_mirror._run.mutated_file`). An MCP server runs with
an arbitrary cwd, so every engine-running handler anchors the process at the caller's
``cwd`` for the duration of the call (``_at``). These handlers are therefore
sequential by contract — call them one at a time (the file-lock in ``_run`` still
prevents corruption if that contract is violated, but results assume a stable cwd).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .adapters import adapter_for
from .brief import build_brief
from .delta import build_delta
from .map import build_full_map
from .plan import build_plan
from .verify import Proposal, verify_proposals

__all__ = ["map_tool", "plan_tool", "brief_tool", "verify_tool", "delta_tool", "bundle_tool"]


@contextmanager
def _at(cwd: str):
    prev = os.getcwd()
    os.chdir(str(Path(cwd).resolve()))
    try:
        yield
    finally:
        os.chdir(prev)


def _now() -> str:
    # timezone.utc (not the 3.11+ datetime.UTC alias) — the package floor is 3.10.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def map_tool(module: str, tests: str, cwd: str = ".", language: str = "python") -> dict:
    """Five-level semantic-coverage map for ``module`` against ``tests``. ``language``
    selects the adapter (python | javascript | typescript | tsx)."""
    with _at(cwd):
        return build_full_map(module, tests, cwd=".", adapter=adapter_for(language)).canonical_dict()


def plan_tool(module: str, tests: str, cwd: str = ".", diff_base: str | None = None,
              language: str = "python") -> dict:
    """Ranked (node, level) gaps + honest assertion stubs. ``diff_base`` scopes to a
    git ref's changed nodes. ``language`` selects the adapter."""
    with _at(cwd):
        cmap = build_full_map(module, tests, cwd=".", adapter=adapter_for(language))
        source = Path(module).read_text(encoding="utf-8")
        changed = None
        if diff_base:
            from ._diff import changed_lines
            changed = changed_lines(module, diff_base, ".")
        return build_plan(cmap, source, changed_lines=changed, diff_base=diff_base).canonical_dict()


def brief_tool(module: str, tests: str, cwd: str = ".", language: str = "python") -> dict:
    """Generation brief: per-gap obligation + stub + the acceptance contract.
    ``language`` selects the adapter."""
    with _at(cwd):
        cmap = build_full_map(module, tests, cwd=".", adapter=adapter_for(language))
        source = Path(module).read_text(encoding="utf-8")
        return build_brief(build_plan(cmap, source)).canonical_dict()


def verify_tool(module: str, tests: str, proposals: list[dict], cwd: str = ".",
                language: str = "python") -> dict:
    """Verify candidate tests legitimately close gaps. ``proposals`` is a list of
    ``{node_id, level, candidate_src, label?}`` — candidate source inline, not a file.
    ``language`` selects the adapter."""
    with _at(cwd):
        cmap = build_full_map(module, tests, cwd=".", adapter=adapter_for(language))
        props = [Proposal(node_id=p["node_id"], level=p["level"],
                          candidate_src=p["candidate_src"], label=p.get("label", ""))
                 for p in proposals]
        return verify_proposals(cmap, module, tests, props, cwd=".").canonical_dict()


def bundle_tool(module: str, tests: str, cwd: str = ".", language: str = "python") -> dict:
    """A self-verifying EvidenceBundle: the SM-5 receipt with the canonical map
    embedded (``{receipt, evidence}``). ``receipt.evidence_ref`` is the sha256 of
    ``evidence``, so a caller can re-verify it standalone. ``language`` selects the
    adapter."""
    with _at(cwd):
        smap = build_full_map(module, tests, cwd=".", adapter=adapter_for(language))
        return smap.to_bundle(_now()).to_dict()


def delta_tool(base_map: dict, head_map: dict) -> dict:
    """Compare two maps (``map_tool`` outputs): closed / regressed / new gaps. Pure —
    no engine run, no cwd needed."""
    return build_delta(base_map, head_map).canonical_dict()
