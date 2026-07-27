---
name: shadow-mirror
description: Systematic validation methodology for proving system correctness through instrumented observation. Trigger on error codes, unexpected behavior, design flaws, quality concerns, reliability questions, or any request to validate/prove functionality, plan tests, or map coverage. Applies the scientific method across seven phases (SM-0 Hypothesize → SM-6 Iterate), with an `sm` engine that maps semantic coverage in Python, JavaScript, TypeScript, and TSX. Spans UI (Playwright), unit/integration (pytest / vitest), and infrastructure (eBPF/Cilium) layers.
---

# Shadow Mirror

A validation framework that casts **shadows** (instrumented traces) and holds up **mirrors** (assertions that reflect expected behavior). Systems are decomposed into an operation tree; assertions accumulate into provable hypotheses about correctness.

Line coverage tells you what *ran*. Shadow Mirror tells you what's *proven* — and what to test next.

## The seven-phase loop (SM-0 .. SM-6)

```
SM-0 HYPOTHESIZE  →  state a falsifiable claim about a symptom
SM-1 INSTRUMENT   →  choose probes that can answer the SM-0 question
SM-2 ASSERT       →  generate predicates that accumulate toward proof
SM-3 EXECUTE      →  cast the shadow: run, collect traces / metrics / outcomes
SM-4 DOCUMENT     →  emit a durable, content-addressable evidence receipt
SM-5 REVIEW       →  meta-validate: coverage, assertion quality, soundness
SM-6 ITERATE      →  refine and loop, or declare done
```

The loop runs in two directions on one engine:

- **Forward — test planning** (SM-0 → SM-1 → SM-2, generatively): given code or a diff, produce a *plan* — the gaps to cover and the assertion stubs to cover them.
- **Backward — coverage mapping** (SM-3 → SM-5, analytically): given existing tests, produce a *map* — the operation tree scored per node, per level, surfacing the blind spots line coverage hides.

> The canonical phase definitions (inputs, outputs, receipt mapping, the phase-count contract) live in `docs/phases.md` in the shadow-mirror repository. This skill is the operational companion; on any discrepancy, `docs/phases.md` is canonical.

## The `sm` engine — the loop, executed

The methodology below is realized by a dependency-free CLI (`pip install 'shadow-mirror[engine]'`; add `[js]` / `[ts]` for JavaScript/TypeScript/TSX). It *consumes* each language's own coverage tool and test runner — `coverage.py` + `pytest` for Python, Istanbul + `vitest` for JS/TS/TSX — never reimplements them, and scores each function across the five levels by **mutation**: a level is `proven` only if a covering test fails when the code is deliberately broken. Line-covered but not noticed = a gap. Pass `--lang {python,javascript,typescript,tsx}` (default `python`) on `sm map` / `sm plan` / `sm verify`.

| Command | Direction | Phases |
|---------|-----------|--------|
| `sm map <mod> --tests <t>` | backward — what's *proven* | SM-3 → SM-5 |
| `sm plan <mod> --tests <t>` | forward — what to test next (ranked gaps + stubs) | SM-0 → SM-2 |
| `sm plan … --brief` | forward — a generation brief + acceptance contract | SM-2 |
| `sm verify … --proposals p.json` | the acceptance gate for generated tests | SM-5 |
| `sm delta base.json head.json` | what a change did to semantic coverage (PR review) | SM-5 |
| `sm map … --html out.html` | a standalone visual map | SM-4 |
| `… --json` / `… --receipt` / `… --bundle` | the canonical receipt, or a self-verifying receipt+map `EvidenceBundle` | SM-4 |

`sm verify` is the check that keeps grounded generation honest: a candidate test is accepted only when re-mapping shows it flips the target gap→proven, it is green on the real code, and nothing previously-proven regresses — so a generated test is never trusted on its word. An agent can call all of these over MCP (`sm-mcp`) — `sm_map` / `sm_plan` / `sm_brief` / `sm_verify` / `sm_bundle` / `sm_delta`, each engine tool taking a `language` param; see the plugin README. Stubs are honest scaffolds (real signature + the level's proof obligation), never a fabricated expected value.

## SM-0: Hypothesize

Given a failure, anomaly, or design question:

1. State the observable symptom precisely.
2. Identify the boundary (what passes vs. what fails).
3. Form a falsifiable claim: "the failure occurs because X, which can be proven by observing Y."

```python
hypothesis = {
    "symptom": "API returns 500 on concurrent requests > 10",
    "boundary": {"passes": "sequential requests", "fails": "concurrent > 10"},
    "claim": "Connection pool exhaustion under load",
    "observable": "Pool size metrics + connection wait times",
}
```

## SM-1: Instrument

Map the operation tree using cyclomatic complexity as the guide; each branch point is a potential instrumentation site. Choose probes justified by the assertion each will feed.

**Decomposition levels** (the axis line coverage can't see) — five, rubric v2:

- **Functional** — does the operation produce correct output?
- **Behavioral** — does it follow expected interaction patterns (is the logic pinned)?
- **Performant** — does it meet timing/resource constraints?
- **Resilient** — does it handle failure modes gracefully?
- **Observable** — is an emitted log/metric actually asserted?

See [references/instrumentation.md](references/instrumentation.md) for tool-specific probes (pytest fixtures, Playwright hooks, eBPF/Cilium, OpenTelemetry).

## SM-2: Assert

Generate predicates that accumulate toward proving or disproving SM-0. Tag each with the operation-tree node and level it covers, so coverage is measurable in SM-5.

See [references/pytest-patterns.md](references/pytest-patterns.md) and [references/playwright-patterns.md](references/playwright-patterns.md) for assertion idioms.

## SM-3: Execute

Cast the shadow — run the instrumented suite and collect traces, metrics, resource use, and per-predicate verdicts.

```bash
pytest tests/ --tb=short -v --json-report --json-report-file=shadow.json   # Python
vitest run --coverage                                                      # JS / TS / TSX
playwright test --trace on --output=shadows/                               # UI / E2E
```

## SM-4: Document

Produce the evidence artifact — durable enough that a third party can reconstruct what was hypothesized, how it was tested, and the verdict.

```
shadow-report/
├── hypothesis.md        # claim + observables
├── operation-tree.md    # cyclomatic map with instrumentation points
├── assertions.json      # all assertions with outcomes
├── traces/              # raw trace data
└── verdict.md           # verified | falsified | inconclusive + reasoning
```

## SM-5: Review

Meta-validate the proof itself.

- **Coverage signal** — node coverage, level distribution (functional/behavioral/performant/resilient), branch coverage, assertion density.
- **Quality** — are predicates falsifiable? redundant? are the boundary/edge cases from SM-0 covered?

See [references/coverage-review.md](references/coverage-review.md) for review heuristics.

## SM-6: Iterate

- **Gaps found** → add instrumentation, generate new assertions.
- **Hypothesis falsified** → form a new hypothesis from the evidence, restart at SM-0.
- **Inconclusive** → deepen instrumentation at ambiguous nodes.
- **Verified** → archive the receipt; consider a regression suite.

## Quick start

```bash
# Install the engine (add [js]/[ts] for JavaScript/TypeScript/TSX)
pip install 'shadow-mirror[engine]'

# Forward (SM-0..SM-2): what to test next — ranked gaps + honest assertion stubs
sm plan src/orders.py --tests tests/test_orders.py

# …or a generation brief + acceptance contract for an agent to close the gaps
sm plan src/orders.py --tests tests/test_orders.py --brief

# Backward (SM-3..SM-5): what's already proven, and the blind spots
sm map src/orders.py --tests tests/test_orders.py
```

The stubs are **honest scaffolds** — the node's real signature + the level's proof
obligation, never a fabricated expected value. Pointing SM at another project? See
`docs/reviewing-a-repo.md` in the shadow-mirror repository.

## Tool integration

| Layer | Tool | Reference |
|-------|------|-----------|
| UI / E2E | Playwright | [references/playwright-patterns.md](references/playwright-patterns.md) |
| Unit / Integration | pytest · vitest | [references/pytest-patterns.md](references/pytest-patterns.md) |
| Network / Infra | eBPF, Cilium | [references/instrumentation.md](references/instrumentation.md) |
| Distributed | OpenTelemetry | [references/instrumentation.md](references/instrumentation.md) |
| Review | coverage heuristics | [references/coverage-review.md](references/coverage-review.md) |
