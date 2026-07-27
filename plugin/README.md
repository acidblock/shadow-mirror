# Shadow Mirror (Claude Code plugin)

Referential introspection for **test planning** and **coverage mapping**.

> Line coverage tells you what *ran*. Shadow Mirror tells you what's *proven* —
> and what to test next.

Shadow Mirror runs a seven-phase scientific-validation loop and anchors coverage
to an **operation tree** scored across five **levels** (functional / behavioral /
performant / resilient / observable) — the semantic dimension that line coverage
structurally cannot see. One engine and the same five levels across **Python,
JavaScript, TypeScript, and TSX** (pytest + coverage.py, vitest + Istanbul).

## What's in the box

| Component | Path | What it does |
|-----------|------|--------------|
| Skill | `skills/shadow-mirror/SKILL.md` | The methodology, auto-triggered on validation/coverage/test-planning requests |
| Command | `commands/shadow-mirror.md` | `/shadow-mirror` — drive the loop on a symptom, module, or diff |
| Agent | `agents/shadow-mirror.md` | A validation subagent that returns an evidence verdict, not reassurance |
| References | `skills/shadow-mirror/references/` | pytest · Playwright · eBPF/Cilium/OTel · coverage-review patterns |
| Engine | `pip install 'shadow-mirror[engine]'` → `sm` | `sm map` / `plan` / `plan --brief` / `verify` / `delta` / `map --bundle` / `map --html` — the loop, executed by mutation (Python · JS · TS · TSX via `--lang`) |
| MCP server | `pip install 'shadow-mirror[mcp,engine]'` → `sm-mcp` | Exposes `sm_map`/`sm_plan`/`sm_brief`/`sm_verify`/`sm_bundle`/`sm_delta` (a `language` param on each engine tool) to an agent host (see "Agent tools over MCP" below) |

## The loop (SM-0 .. SM-6)

```
SM-0 Hypothesize  →  state a falsifiable claim about a symptom
SM-1 Instrument   →  choose probes that can answer the SM-0 question
SM-2 Assert       →  generate predicates that accumulate toward proof
SM-3 Execute      →  run, collect traces / metrics / outcomes
SM-4 Document     →  emit a durable, content-addressable evidence receipt
SM-5 Review       →  meta-validate: coverage, assertion quality, soundness
SM-6 Iterate      →  refine and loop, or declare done
```

Run forward for **test planning** (SM-0→SM-2, generative: gaps + stubs), backward
for **coverage mapping** (SM-3→SM-5, analytic: the map + the blind spots).

The canonical phase definitions live in [`docs/phases.md`](../docs/phases.md) at
the repo root — this plugin is the operational companion.

## Install

```bash
claude plugin marketplace add acidblock/shadow-mirror
claude plugin install shadow-mirror@shadow-mirror
```

Then `/shadow-mirror` to start, or just ask Claude to validate, plan tests for,
or map coverage on something — the skill triggers automatically.

For the **engine** (the `sm` CLI that actually maps/plans/verifies by mutation),
install the package — it stays dependency-free, consuming each language's own
coverage + test runner (`coverage.py`/`pytest` for Python; Istanbul/`vitest` for
JS/TS/TSX) out of process:

```bash
pip install 'shadow-mirror[engine]'
sm map your_module.py --tests tests/test_your_module.py
```

For non-Python targets, install the `[js]` or `[ts]` extra and pass
`--lang {javascript,typescript,tsx}` (works on `sm map`/`plan`/`verify`). A full
walkthrough — the prerequisite, the review flow, and the self-verifying
`EvidenceBundle` you hand back — is in
[`docs/reviewing-a-repo.md`](../docs/reviewing-a-repo.md).

## Agent tools over MCP

`sm-mcp` is a stdio MCP server exposing the engine to an agent host —
`sm_map`, `sm_plan`, `sm_brief`, `sm_verify`, `sm_bundle`, `sm_delta`, each engine
tool taking a `language` param (`python` | `javascript` | `typescript` | `tsx`). To
wire it into this plugin, the plugin ships [`.mcp.json`](.mcp.json) (which points at
a per-plugin virtualenv) plus a one-time setup script:

```bash
# build the plugin's MCP venv (installs shadow-mirror[mcp,engine] from the repo)
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-mcp.sh"
# then reconnect the server:
/reload-plugins        # or restart Claude Code; check it under /mcp
```

`scripts/setup-mcp.sh` `pip install`s **from the git repository**, so no PyPI
publication is required — but the repo is **private**, so you need git access
(SSH key or a token) for the install to succeed. The tools also run the engine, so
the venv pulls `[mcp,engine]` together — add `[js]`/`[ts]` for JavaScript/TypeScript/TSX targets.

> **Status — unverified wiring.** The CLI (`sm`/`sm-mcp`) is tested and supported.
> The plugin-side `.mcp.json` + setup-script wiring is provided as the documented
> path but has not been validated against every Claude Code version — confirm via
> `/mcp` after setup, and see the exact server config in `.mcp.json`. Until you run
> the setup script, the server will simply show as not-connected (no harm done).

## License

Apache-2.0.
