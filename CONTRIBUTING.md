# Contributing to Shadow Mirror

Thanks for your interest! This project welcomes issues, discussion, and pull
requests. This document covers the practical parts: getting a dev environment
running, the quality bar CI enforces, and how changes land.

Please note the [Code of Conduct](CODE_OF_CONDUCT.md) — participation implies
acceptance. Security reports go through the [security policy](SECURITY.md),
never the public issue tracker.

## Dev setup

```bash
git clone https://github.com/acidblock/shadow-mirror.git
cd shadow-mirror
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test,js,ts,mcp]" "ruff==0.16.0"
```

That gives you the full engine (Python + JS/TS/TSX adapters), the MCP server,
pytest, and the pinned linter. For the cross-language conformance tests you
also need Node 20+ and the locked fixture deps:

```bash
cd tests/fixtures/conformance_js && npm ci && cd -
```

## Running the checks

```bash
ruff check .                                # lint — see "the formatting bar" below
python -m pytest tests/ -q                  # full suite
SM_REQUIRE_JS=1 python -m pytest tests/ -q  # fail (not skip) if the JS toolchain is missing
```

Without Node/`npm ci`, the JS/TS conformance tests **skip**; CI runs them with
`SM_REQUIRE_JS=1`, so make them pass locally if your change touches the
adapters or the SPI. One suite (`test_constraints.py`'s C4 scan) needs a
denylist file that is deliberately kept out of the repo — it skips for you and
for fork PRs; only trusted CI enforces it. That skip is expected, not a
problem with your setup.

### The formatting bar (unusual — read this)

There is **no formatter** in this repo. The code is hand-formatted (~100-char
lines), and the lint bar is exactly ruff's classic default set, pinned in
`pyproject.toml` (`select = ["E4", "E7", "E9", "F"]`) with `ruff==0.16.0` in
CI. Please don't run `black` or `ruff format` over existing files or widen the
rule set in a PR — match the surrounding style by hand instead. Comment
density is high and deliberate: comments state invariants and reasoning, not
line-by-line narration.

## Design constraints that shape PRs

The invariant registry is [`docs/constraints.md`](docs/constraints.md) (C1–C5).
The two that most often affect contributions:

- **C1 — zero runtime dependencies.** The core `shadow_mirror` package imports
  only the standard library; coverage.py, pytest, vitest, and the MCP SDK are
  *tools or extras*, consumed out-of-process or behind optional imports. A test
  enforces this.
- **C3 — zero rewrites for adopters.** `sm` must work on an existing test
  suite without annotations or restructuring. Features that require the target
  project to change don't land.

Claims should be *measured, not assumed* — that's what
[`docs/spikes/`](docs/spikes/) is: small experiments with recorded evidence.
If your change rests on a non-obvious behavioral claim (of coverage.py, of
Istanbul, of the AST round-trip), a short spike note is welcome alongside it.

## Landing a change

1. Branch from `main` (`feat/...`, `fix/...`, `docs/...`).
2. Commit in [conventional-commit](https://www.conventionalcommits.org) style:
   `fix(run): ...`, `feat(map): ...`, `docs: ...` — it's what the history uses.
3. Tests come with the change: a bug fix carries a regression test that fails
   before the fix; a feature carries tests for its contract. (PR #1 is the
   house pattern: the SIGTERM test fails on the pre-fix engine.)
4. Open a PR against `main` and fill in the template. `main` is protected:
   both CI checks (`test (3.10)`, `test (3.12)`) must pass, history is linear
   (PRs are squash-merged), force pushes are blocked, and unresolved review
   threads block merge.

Small, focused PRs review fastest. For anything large or design-shaped, open
an issue first so the approach can be agreed on before you invest in it.

## What's useful right now

[`ROADMAP.md`](ROADMAP.md) is the honest work list, including known engine
gaps. Reproducible bug reports with a minimal module + test file are
especially valuable — the issue form asks for exactly the inputs
`sm map` needs to replay your case.
