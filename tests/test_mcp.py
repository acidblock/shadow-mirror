"""Tests for the MCP surface.

The *handlers* (`mcp_tools`) import no `mcp` and carry the logic, so they're tested
directly — fast for the pure one (delta), slow for the engine-running ones. The
*server* (`mcp_server`) is the thin wiring: a smoke check that the tools register
(no live transport handshake — that's flaky and env-dependent). Plus the C1 guard:
importing `shadow_mirror` must not pull `mcp`.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from shadow_mirror import mcp_tools

ROOT = Path(__file__).resolve().parent.parent
MOD = "tests/fixtures/resilient_demo/orders.py"
TST = "tests/fixtures/resilient_demo/test_orders.py"


def test_c1_importing_package_does_not_pull_mcp():
    # The package must stay dependency-free: a fresh `import shadow_mirror` (and its
    # submodules a user would touch) must not transitively import the mcp SDK.
    code = ("import shadow_mirror, shadow_mirror.map, shadow_mirror.mcp_tools, sys;"
            "assert 'mcp' not in sys.modules, sorted(m for m in sys.modules if 'mcp' in m)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_delta_tool_is_pure_and_needs_no_cwd():
    from tests.test_delta import BASE, HEAD
    out = mcp_tools.delta_tool(BASE, HEAD)
    assert len(out["regressed"]) == 1 and len(out["closed"]) == 1 and len(out["new_gaps"]) == 1


@pytest.mark.slow
def test_map_tool_anchors_cwd_even_when_called_from_elsewhere(tmp_path, monkeypatch):
    # The engine resolves/mutates relative to the PROCESS cwd. Move the process cwd
    # away, then call map_tool with cwd=ROOT — it must re-anchor and still work.
    monkeypatch.chdir(tmp_path)
    out = mcp_tools.map_tool(MOD, TST, cwd=str(ROOT))
    assert out["rubric_version"] == 2
    assert any(n["node_id"].endswith("::charge") for n in out["nodes"])


@pytest.mark.slow
def test_brief_tool_returns_acceptance_contract():
    out = mcp_tools.brief_tool(MOD, TST, cwd=str(ROOT))
    assert "acceptance" in out and out["gaps"]
    assert "map_ref" in out and "plan_ref" in out


@pytest.mark.slow
def test_verify_tool_takes_inline_candidate_source():
    # a legitimate closer for charge/functional, candidate SOURCE inline (no file)
    node_id = "tests/fixtures/resilient_demo/orders.py::charge"
    proposals = [{"node_id": node_id, "level": "functional", "label": "ok",
                  "candidate_src": "def test_c():\n    import orders\n    assert orders.charge(5) == 5\n"}]
    out = mcp_tools.verify_tool(MOD, TST, proposals, cwd=str(ROOT))
    assert out["verdicts"][0]["accepted"] is True


def test_server_registers_all_tools():
    pytest.importorskip("mcp")
    from shadow_mirror.mcp_server import build_server
    server = build_server()
    names = {t.name for t in server._tool_manager.list_tools()}
    assert names == {"sm_map", "sm_plan", "sm_brief", "sm_verify", "sm_bundle", "sm_delta"}


def test_adapter_for_selects_by_language():
    from shadow_mirror.adapters import adapter_for
    assert adapter_for("python").language == "python"
    with pytest.raises(ValueError):
        adapter_for("cobol")
    # JS family is lazy-loaded behind the [js]/[ts] extra (tree-sitter)
    pytest.importorskip("tree_sitter_javascript")
    assert adapter_for("javascript").language == "javascript"
    pytest.importorskip("tree_sitter_typescript")
    assert adapter_for("typescript").language == "typescript"
    assert adapter_for("tsx").language == "tsx"
    assert adapter_for("ts").language == "typescript"  # alias


@pytest.mark.slow
def test_bundle_tool_returns_self_verifying_bundle():
    from shadow_mirror import EvidenceBundle
    out = mcp_tools.bundle_tool(MOD, TST, cwd=str(ROOT))
    assert set(out) == {"receipt", "evidence"}
    assert out["evidence"]["rubric_version"] == 2
    assert EvidenceBundle.from_dict(out).verified  # self-verifying across the MCP boundary
    assert out["receipt"]["instrumentation"][0] == "python"  # language-correct provenance
