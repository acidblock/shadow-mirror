# Reviewing another repo — quickstart

Point Shadow Mirror at a project, get its semantic-coverage map, and hand back a
self-verifying review artifact. Works on an existing test suite with **zero
rewrites and zero required annotations** (C3).

## Prerequisite (read this first)

`sm map` runs the target's **own test suite under coverage** — so the project's
full dependency tree must be installed first, exactly as if you were running its
tests. If a target import fails for a missing dependency, that is why (install the
target's test/dev deps, then re-run). SM consumes the language's coverage + test
runner; it never reimplements them.

## Python — three commands

```bash
cd their-repo
pip install -e .                       # the TARGET's own test deps (or: poetry install, -r requirements-dev.txt, …)
pip install 'shadow-mirror[engine]'    # the sm engine (pulls coverage.py + pytest)
sm map src/orders.py --tests tests/test_orders.py
```

## JavaScript / TypeScript / TSX

```bash
cd their-repo
npm ci                                 # the target's vitest + @vitest/coverage-istanbul
pip install 'shadow-mirror[js]'        # or '[ts]' for typescript / tsx
sm map src/orders.ts --tests src/orders.test.ts --lang typescript
```

`--lang {python,javascript,typescript,tsx}` (default `python`) also applies to
`sm plan` and `sm verify`.

## The review flow

```bash
# 1. what's proven, where the gaps are (per module)
sm map <module> --tests <tests>

# 2. what to test next — ranked gaps + honest assertion stubs
sm plan <module> --tests <tests>

# 3. scope the review to a PR's changed nodes only
sm plan <module> --tests <tests> --diff main

# 4. gate a PR on lost proof — produce a base + head map, then compare
sm map <module> --tests <tests> --json > head.json
git stash && sm map <module> --tests <tests> --json > base.json && git stash pop
sm delta base.json head.json --fail-on-regression       # exit 1 if a proven cell regressed
```

## The deliverable — a self-verifying EvidenceBundle

```bash
sm map <module> --tests <tests> --bundle review.json
#   bundle → review.json  (sha256:…, verified=True)
```

`review.json` is the portable hand-back: a **receipt** with the **canonical map
embedded**. It is self-verifying — anyone can re-check it without re-running the
engine:

```python
from shadow_mirror import EvidenceBundle
EvidenceBundle.from_json(open("review.json").read()).verified   # True
```

What it carries, in the project's own vocabulary:

- **outcome** (receipt) — `verified` (zero gaps) or `inconclusive` (gaps remain).
  This is the repo-level result.
- **verdicts** (embedded map, per `(node, level)`) — `proven` ·
  `gap-unasserted` (runs, unnoticed) · `gap-unexercised` (never runs) ·
  `no-signal` (ran, but no covering test resolved — indeterminate, not a gap) ·
  `n/a`. The full rubric is in [`coverage-levels.md`](coverage-levels.md).
- **provenance** (receipt `instrumentation`) — language-correct and version-stamped
  (e.g. `["typescript", "tree-sitter@…", "tree-sitter-typescript@…",
  "vitest+istanbul(out-of-process)", "sm-mutation@…", "sm-rubric@v2"]`), so the
  bundle records *what* produced it. See [`evidence-bundle.md`](evidence-bundle.md).

## Agent-driven

- **In a Claude session inside the repo** (plugin installed): `/shadow-mirror`, or
  just ask — "map coverage on `src/orders.ts`" — the skill triggers and drives the
  loop.
- **Over MCP**: run `sm-mcp` and call `sm_map` / `sm_plan` / `sm_bundle` with a
  `language` param. Every engine-running tool anchors to the `cwd` you pass, so the
  server works against any repo regardless of its own directory.

## Reading the result

A level is `proven` only if a covering test **fails when the code is deliberately
broken** (mutation). Line-covered but un-noticed is a gap — the blind spot line
coverage cannot see. The five levels and the rubric are in
[`coverage-levels.md`](coverage-levels.md); a full grounded round-trip (map → plan
→ generate → verify) is in [`examples/grounded-loop.md`](examples/grounded-loop.md).
