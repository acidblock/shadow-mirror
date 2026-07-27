"""MCP stdio server — exposes Shadow Mirror as tools an agent can call directly.

This is the *only* module that imports the ``mcp`` SDK (the optional ``[mcp]``
extra). The tool logic lives in :mod:`shadow_mirror.mcp_tools` (no ``mcp`` import),
so importing the ``shadow_mirror`` package never pulls ``mcp`` and the runtime stays
dependency-free (C1). This module is not imported by the package ``__init__``.

Run::

    python -m shadow_mirror.mcp_server      # or the `sm-mcp` console script

then point an MCP client (e.g. an agent host) at that stdio command.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import mcp_tools

__all__ = ["build_server", "main"]

# A self-describing enum so a purpose-agnostic caller sees the valid languages in the
# tool schema (not a free-form string). The adapter is selected per call.
Language = Literal["python", "javascript", "typescript", "tsx"]


def build_server() -> FastMCP:
    """Construct the server with all Shadow Mirror tools registered."""
    server = FastMCP("shadow-mirror")

    @server.tool()
    def sm_map(module: str, tests: str, cwd: str = ".", language: Language = "python") -> dict:
        """Five-level semantic-coverage map for `module` against its `tests`.
        `module`/`tests` are paths relative to `cwd` (the project root). `language`
        selects the source language / adapter."""
        return mcp_tools.map_tool(module, tests, cwd, language)

    @server.tool()
    def sm_plan(module: str, tests: str, cwd: str = ".",
                diff_base: str | None = None, language: Language = "python") -> dict:
        """Ranked (node, level) coverage gaps + honest assertion stubs.
        `diff_base` scopes the plan to nodes changed vs a git ref."""
        return mcp_tools.plan_tool(module, tests, cwd, diff_base, language)

    @server.tool()
    def sm_brief(module: str, tests: str, cwd: str = ".", language: Language = "python") -> dict:
        """Generation brief: per-gap proof obligation + stub + the acceptance
        contract a candidate test must satisfy to be accepted."""
        return mcp_tools.brief_tool(module, tests, cwd, language)

    @server.tool()
    def sm_verify(module: str, tests: str, proposals: list[dict],
                  cwd: str = ".", language: Language = "python") -> dict:
        """Verify candidate tests legitimately close gaps. `proposals` is a list of
        {node_id, level, candidate_src, label?} — the test SOURCE inline, not a file.
        Returns per-proposal verdicts + a joint-safety check on the accepted set."""
        return mcp_tools.verify_tool(module, tests, proposals, cwd, language)

    @server.tool()
    def sm_bundle(module: str, tests: str, cwd: str = ".", language: Language = "python") -> dict:
        """A self-verifying EvidenceBundle for `module`: the SM-5 receipt with the
        canonical map embedded (`{receipt, evidence}`). `receipt.evidence_ref` is the
        sha256 of `evidence`, so a caller can re-verify the bundle standalone."""
        return mcp_tools.bundle_tool(module, tests, cwd, language)

    @server.tool()
    def sm_delta(base_map: dict, head_map: dict) -> dict:
        """Compare two `sm_map` outputs (base vs head): gaps closed, proven cells
        regressed to gaps, and new gaps the change introduced."""
        return mcp_tools.delta_tool(base_map, head_map)

    return server


def main() -> None:  # pragma: no cover - stdio runloop; exercised by an MCP client
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
