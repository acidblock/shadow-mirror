# Shadow Mirror — Interface Reference

The complete public surface of `shadow-mirror` v0.2.0, in one place: the CLI,
the Python library API, the MCP tools, the language-adapter SPI, and the wire
formats. Anything not listed here is internal and may change without notice.

On any discrepancy between this document and the per-format specs it links
(`docs/receipt-format-v1.md`, `docs/evidence-bundle.md`, `docs/coverage-levels.md`,
`docs/phases.md`), the linked spec is canonical.

---

## 1. Installation surfaces

| Extra | Installs | Enables |
|-------|----------|---------|
| (none) | pure-stdlib data model | `Phase`, `ReceiptV1`, `EvidenceBundle` — zero runtime dependencies (C1) |
| `[engine]` | `coverage>=7`, `pytest>=7` | the `sm` CLI on Python targets |
| `[js]` | `tree-sitter`, `tree-sitter-javascript` | `--lang javascript` |
| `[ts]` | `tree-sitter`, `tree-sitter-typescript` | `--lang typescript` / `--lang tsx` |
| `[mcp]` | `mcp>=1.0` | the `sm-mcp` stdio server |

Console scripts: `sm = shadow_mirror.cli:main`, `sm-mcp = shadow_mirror.mcp_server:main`.
Python floor: 3.10. The engine *consumes* each language's own coverage tool and
test runner out-of-process (coverage.py + pytest; Istanbul + vitest via `npx`) —
they are tools in the target environment, never import-time dependencies (C1).

---

## 2. CLI — `sm`

Four subcommands. Common arguments on `map`, `plan`, and `verify`:

| Argument | Meaning |
|----------|---------|
| `module` (positional) | path to the source module, relative to `--cwd` |
| `--tests PATH` (required) | the test target for that module |
| `--cwd DIR` | working directory for the test run (default `.`) — the target project's root, with its deps installed |
| `--lang {python,javascript,typescript,tsx}` | language adapter (default `python`) |
| `--json` | emit the canonical JSON instead of the text view |
| `--fail-on-gap` | exit 1 if any level-gap is found |
| `-v` / `-vv` | per-node verdicts (INFO) / per-mutant kill-survive (DEBUG), to stderr |

### `sm map` — backward: what's proven

```
sm map MODULE --tests TESTS [--receipt PATH] [--bundle PATH] [--html PATH]
```

Builds the five-level semantic-coverage map (§6.1). `--receipt` writes an SM-5
`ReceiptV1`; `--bundle` writes a self-verifying `EvidenceBundle`; `--html` writes
a standalone, dependency-free HTML view. Exit: `1` iff `--fail-on-gap` and gaps
exist, else `0`.

### `sm plan` — forward: what to test next

```
sm plan MODULE --tests TESTS [--diff BASE] [--brief] [--receipt PATH]
```

Pure post-processing over the map: ranks gaps by node complexity, then deficit
(gap levels / applicable levels), then verdict, and scaffolds an honest assertion
stub per gap (real signature + `<PLACEHOLDER>`s, never a fabricated oracle).

- `--diff BASE` scopes the plan to nodes changed vs git ref `BASE`
  (maps `git diff --unified=0 BASE` to nodes by line range). Diff failure → exit `2`.
- `--brief` emits a generation brief instead (§6.4): per-gap obligation + stub
  under the acceptance contract — machine-consumable context for a test generator.
- `--receipt` writes an SM-2 `ReceiptV1` (`outcome: inconclusive`).

Exit: `1` iff `--fail-on-gap` and the plan has items, else `0`.

### `sm verify` — the acceptance gate

```
sm verify MODULE --tests TESTS --proposals MANIFEST.json [--receipt PATH]
```

`MANIFEST.json` is a list of `{node_id, level, candidate (file path), label?}`.
Each candidate is checked **independently** against the baseline suite + map:

1. **VALID** — the combined suite (existing ∪ candidate) is green on the
   unmutated module (the green-gate: a red candidate would read as
   "always killed" and vacuously close every gap).
2. **CLOSED** — appending it flips the targeted cell gap→proven under re-map.
3. **NO REGRESSION** — no previously-proven cell drops.

When ≥2 proposals are accepted, a final **joint gate** appends them all and
re-maps once (`safe` = the set holds *together*). Exit: `0` iff every proposal
is accepted and the joint check is safe, else `1`. Nothing auto-merges.

### `sm delta` — what a change did

```
sm delta BASE.json HEAD.json [--json | --markdown] [--receipt PATH]
         [--fail-on-regression] [--gate-complexity N]
```

Pure comparison of two `sm map --json` payloads — no engine run, no git.
Buckets: **closed** (gap→proven), **regressed** (proven→gap), **new_gaps**
(gaps on nodes the change introduced). `--markdown` emits a PR-comment-ready
delta with a hidden sticky-comment marker. Gates are opt-in (C3):
`--fail-on-regression` → exit 1 on any regression; `--gate-complexity N` → also
exit 1 on a new gap at node complexity ≥ N. `--receipt` writes an SM-5
`ReceiptV1` carrying `base_ref` / `head_ref`.

---

## 3. Python library API

### 3.1 Top-level (`shadow_mirror`) — pure stdlib, no dependencies

```python
from shadow_mirror import (
    __version__,            # "0.2.0"
    Phase, PHASES, PHASE_NAMES, name_for,   # SM-0..SM-6 enumeration (docs/phases.md)
    ReceiptV1, Outcome, SCHEMA_VERSION,     # frozen v1 receipt (docs/receipt-format-v1.md)
    EvidenceBundle,                         # self-verifying receipt+map (docs/evidence-bundle.md)
)
```

- `ReceiptV1` — frozen, kw-only dataclass; fields `phase`, `hypothesis`,
  `assertion`, `outcome`, `ts`, `evidence_ref`, `instrumentation=()`,
  `schema_version="1.0"`. Accepts enums or their string values. Guarantee:
  `ReceiptV1.from_json(r.to_json()) == r` (sorted-key JSON; unknown keys
  ignored on read — v1 leniency).
- `Outcome` — exactly `verified | falsified | inconclusive`. Execution alone is
  never `verified`; verification requires an assertion that could have failed.
- `EvidenceBundle` — frozen `{receipt, evidence}` pair.
  `bundle.verified ⇔ sha256(canonical(evidence)) == receipt.evidence_ref`.
  Tamper-evident for inconsistency, not tamper-proof (no signature in v1).

### 3.2 Engine modules (stable entry points)

| Import | Public names | Role |
|--------|--------------|------|
| `shadow_mirror.map` | `build_full_map`, `CoverageMap`, `MapNode`, `LevelVerdict` | build the five-level map |
| `shadow_mirror.plan` | `build_plan`, `Plan`, `PlanItem` | rank gaps + scaffold stubs |
| `shadow_mirror.brief` | `build_brief`, `GenerationBrief`, `GapBrief`, `ACCEPTANCE` | the generation brief + acceptance contract |
| `shadow_mirror.verify` | `verify_proposals`, `Proposal`, `Verdict`, `VerificationReport` | the acceptance gate |
| `shadow_mirror.closure` | `check_closure`, `check_joint_closure`, `ClosureResult`, `JointClosure` | the single-candidate / joint closure primitives `verify` composes |
| `shadow_mirror.delta` | `build_delta`, `MapDelta`, `CellChange` | compare two canonical maps |
| `shadow_mirror.adapters` | `adapter_for`, `PythonAdapter` | adapter registry (§5) |
| `shadow_mirror.spi` | `LanguageAdapter`, `Mutant`, `Coverage`, `ModuleModel`, `TestId`, `LEVELS`, `MUTATION_LEVELS`, `NODE_ID_FUNCTION`, `NODE_ID_BRANCH`, `SHAPE_HASH_CONTRACT` | the language boundary (§5) |
| `shadow_mirror.html` | `render_html` | standalone HTML map view |

Result objects share a uniform shape: `canonical_dict()` → the canonical
mapping; `canonical_json()` → sorted-key, no-whitespace JSON;
`evidence_ref()` → `"sha256:" + sha256(canonical_json)`; `to_receipt(ts)` →
a `ReceiptV1` attesting it; `to_text()` → the human view. `CoverageMap` adds
`gaps()`, `to_bundle(ts)`, and `to_markdown()`-style views where applicable.

Logging: the package logs under the `shadow_mirror` logger and attaches **no
handler on import** — silent as a library; the CLI's `-v/-vv` attaches one.

### 3.3 Typical embed

```python
from shadow_mirror.adapters import adapter_for
from shadow_mirror.map import build_full_map
from shadow_mirror.plan import build_plan

smap = build_full_map("src/orders.py", "tests/test_orders.py",
                      cwd=".", adapter=adapter_for("python"))
plan = build_plan(smap, open("src/orders.py").read())
```

---

## 4. MCP tools — `sm-mcp`

A stdio server (`sm-mcp`, or `python -m shadow_mirror.mcp_server`) exposing six
tools. Handlers live in `shadow_mirror.mcp_tools` (never imports `mcp`, so they
are callable/testable without the SDK); `shadow_mirror.mcp_server`
(`build_server`, `main`) is the thin wiring.

| Tool | Parameters | Returns |
|------|------------|---------|
| `sm_map` | `module`, `tests`, `cwd="."`, `language="python"` | the canonical map (§6.1) |
| `sm_plan` | `module`, `tests`, `cwd`, `diff_base=None`, `language` | the canonical plan (§6.3) |
| `sm_brief` | `module`, `tests`, `cwd`, `language` | the generation brief (§6.4) |
| `sm_verify` | `module`, `tests`, `proposals`, `cwd`, `language` | the verification report (§6.5) |
| `sm_bundle` | `module`, `tests`, `cwd`, `language` | a self-verifying `EvidenceBundle` dict (§6.2) |
| `sm_delta` | `base_map`, `head_map` (two `sm_map` outputs) | the canonical delta (§6.6) — pure, no engine run |

Contract notes:

- `language` ∈ `python | javascript | typescript | tsx` on every engine-running tool.
- Every engine-running tool **anchors at the caller's `cwd`** for the duration of
  the call — pass the target project root; the server's own cwd is irrelevant.
- Handlers are **sequential by contract** — one call at a time (a file lock
  prevents corruption if violated, but results assume a stable cwd).
- `sm_verify` takes candidate test **source inline**:
  `proposals = [{node_id, level, candidate_src, label?}]` — no files, unlike the
  CLI manifest which references candidate *files*.

---

## 5. Language-adapter SPI (`shadow_mirror.spi`)

The boundary between the language-agnostic engine core (verdict logic + wire
format) and per-language signal suppliers. `adapter_for(language)` resolves
`python` eagerly and `javascript`/`typescript`/`tsx` (aliases `js`/`ts`/`jsx`)
lazily — a missing extra raises a clear `RuntimeError`, not an ImportError.

`LanguageAdapter` (a `runtime_checkable` `Protocol`; stateless per call):

| Method | Supplies |
|--------|----------|
| `language: str` | recorded in the receipt's provenance |
| `discover(source, module_path) → ModuleModel` | the operation tree: `FunctionNode`s (with adapter-computed `complexity`, `return_lines`, `shape_hash`) + `ErrorBranch`es |
| `coverage(module_path, tests_path, cwd) → Coverage` | per-test line attribution |
| `mutants(level, source, node) → tuple[Mutant, ...]` | mutants for one node at one level ∈ `MUTATION_LEVELS`; empty tuple ⇒ no signal at this node |
| `timing_tests(tests_path, cwd) → frozenset[TestId]` | tests asserting a time/resource bound — performant is **detection, not mutation** |
| `run_all(tests_path, cwd) → int` | whole-suite exit code (green-gate primitive) |
| `run_selected(test_ids, cwd) → int` | exit code of just those tests (kill detection) |
| `apply(module_path, mutated_source) → ContextManager` | crash-hardened source overlay; also serves candidate-source overlay for verify/closure |
| `toolchain() → tuple[str, ...]` | version-stamped instrumentation identity for the receipt (not hashed into `evidence_ref`) |

Core-specified contracts (adapter-computed, never adapter-defined — receipts
must be comparable across languages):

- **Node identity** — function: `{path}::{qualname}`; error branch:
  `{path}::{qualname}#{kind}:{ordinal}` (Nth branch of that kind in source
  order — stable under reformatting, not reordering).
- **`shape_hash`** — `sha256(normalized-structure, no line numbers)[:16]`: a
  rename-tolerant structural fingerprint; same structure → same hash,
  cross-checkout.
- **`Mutant` well-formedness** — the adapter has re-parsed `mutated_source` and
  confirmed no parse error before returning it (an unparseable mutant is
  indistinguishable from a kill → false `proven`). Drop, never yield, malformed.
- **`Coverage.executed_lines` full-span expansion** — every executed statement
  contributes its whole start..end line range (start-line-only misreads
  multi-line statements as `gap-unexercised`).
- **`TestId` round-trip** — whatever appears in `Coverage.line_tests` and
  `timing_tests` must be consumable by the *same* adapter's `run_selected`,
  addressable unambiguously (anchored, not substring).

Levels: `LEVELS = (functional, behavioral, performant, resilient, observable)`;
`MUTATION_LEVELS` excludes `performant`. Functional/behavioral/observable
mutate a `FunctionNode`; resilient mutates an `ErrorBranch` (the engine
aggregates a function's branches worst-first).

---

## 6. Wire formats (canonical JSON payloads)

All canonical payloads serialize as sorted-key, no-whitespace JSON;
`evidence_ref` is always `"sha256:" + sha256(canonical_json)`.

### 6.1 Coverage map (`sm map --json` / `sm_map`)

```jsonc
{
  "rubric_version": 2,                      // v2 = the five-level rubric
  "module": "src/orders.py",
  "line_coverage": {"covered_lines": 41, "num_statements": 44},
  "nodes": [                                // sorted by node_id
    {
      "node_id": "src/orders.py::charge",
      "complexity": 2,
      "executed": true,
      "levels": {"functional": "proven", "behavioral": "gap-unasserted",
                 "performant": "n/a", "resilient": "no-signal",
                 "observable": "gap-unexercised"}
    }
  ]
}
```

Verdict vocabulary (one cell = one node × one level):

| Verdict | Meaning |
|---------|---------|
| `proven` | a covering test *notices when the cell is broken* (every mutant killed / the bound asserted) |
| `gap-unasserted` | the code runs under the suite, but no test fails when it's mutated |
| `gap-unexercised` | the relevant line(s) never run under the suite |
| `no-signal` | the code ran but no covering test could be resolved (or a run branch yields no mutants) — an indeterminate state, **not** a gap |
| `n/a` | the level doesn't apply to this node (no mutation sites / no timing applicability) |

A level is `proven` only by mutation-and-rerun (or, for `performant`, by a
covering test that asserts a time bound). Line-covered-but-unnoticed is a gap —
the semantic deficit line coverage cannot see.

### 6.2 EvidenceBundle

`{"receipt": <ReceiptV1 dict>, "evidence": <canonical map>}` — re-verifiable
standalone: recompute `sha256(canonical(evidence))` and compare to
`receipt.evidence_ref`. See `docs/evidence-bundle.md`.

### 6.3 Plan

`{module, source_evidence_ref, items: [{node_id, level, verdict, complexity,
deficit, applicable, signature, stub}], diff_base?}` — items pre-ranked;
`diff_base` present only when `--diff` scoped the plan (absence keeps the
non-diff `evidence_ref` unchanged).

### 6.4 Generation brief

`{module, map_ref, plan_ref, acceptance, gaps: [...], diff_base?}` — provenance
chain `map_ref → plan_ref → brief_ref`. `acceptance` is the literal contract: a
candidate is ACCEPTED iff VALID (green on the unmutated module) ∧ CLOSED
(flips its cell gap→proven) ∧ NO REGRESSION (no proven cell drops).

### 6.5 Verification report

`{module, map_ref, verdicts: [...], joint?: {n, valid, all_closed, safe,
regressions, reason}}` — `joint` present when ≥2 proposals were accepted.

### 6.6 Delta

`{module, base_ref, head_ref, closed: [...], regressed: [...], new_gaps: [...]}`
— each cell change carries the node, level, complexity, and the
before/after verdicts.

### 6.7 ReceiptV1 (schema `"1.0"`, frozen)

Eight fields: `schema_version`, `phase` (`"SM-0"`…`"SM-6"`), `hypothesis`,
`instrumentation` (array), `assertion`, `outcome`
(`verified|falsified|inconclusive`), `ts` (ISO-8601 UTC), `evidence_ref`.
Sorted-key JSON round-trip guaranteed; unknown keys ignored on read.
Canonical spec: `docs/receipt-format-v1.md`.

---

## 7. Claude Code plugin surface

The repo doubles as a one-plugin marketplace (`.claude-plugin/marketplace.json`).

| Component | Path | Interface |
|-----------|------|-----------|
| Skill | `plugin/skills/shadow-mirror/` | auto-triggers on validation / coverage / test-planning requests |
| Command | `plugin/commands/shadow-mirror.md` | `/shadow-mirror` — drive the loop on a symptom, module, or diff |
| Agent | `plugin/agents/shadow-mirror.md` | `shadow-mirror` validation subagent — returns an evidence verdict |
| MCP wiring | `plugin/.mcp.json` + `plugin/scripts/setup-mcp.sh` | per-plugin venv running `sm-mcp` (§4) |

---

## 8. Standing constraints (the laws this interface obeys)

| # | Constraint | Interface consequence |
|---|-----------|------------------------|
| C1 | Consume, don't rebuild | runtime deps stay empty; coverage/test tools run out-of-process |
| C2 | Trust anchor | `sm`'s covered-line count equals the coverage tool's, exactly |
| C3 | Additive onboarding | runs on an existing suite with zero rewrites; all CI gates are opt-in flags |
| C4 | Pristine / standalone | no foreign-project references in any shipped artifact |
| C5 | Grounded generation is measurable | acceptance is verified by re-mapping (`closure` / `verify`), never taken on a candidate's word |

Registry with enforcement status: `docs/constraints.md`.
