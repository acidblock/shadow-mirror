# Roadmap — Shadow Mirror

**Single roadmap.** Supersedes all prior.

**Goal.** Make Shadow Mirror the tool a developer — *or an AI agent* — reaches
for first to answer two questions:

1. **Test planning** — "Here is this code / this diff. What should be tested,
   at what depth?"
2. **Coverage mapping** — "Here are these tests. What do they actually
   *prove*, and where are the blind spots that line coverage hides?"

---

## The thesis (one sentence)

> **Line coverage tells you what *ran*. Shadow Mirror tells you what's
> *proven* — and what to test next.**

A line at 100 % coverage can carry zero meaningful assertions. `pytest-cov`
structurally cannot see that. Shadow Mirror anchors coverage to an **operation
tree** and scores it across five **levels** (functional / behavioral /
performant / resilient / observable — rubric v2), so it measures *semantic*
coverage — the gap between "executed" and "proven."

One engine, run in two directions — mapping exactly onto the SM loop:

| Direction | Produces | SM phases |
|-----------|----------|-----------|
| **Forward — test planning** | a *plan*: ranked gaps + assertion/test stubs | SM-0 → SM-1 → SM-2 run *generatively* |
| **Backward — coverage mapping** | a *map*: tree scored per node, per level | SM-3 → SM-4 → SM-5 run *analytically* (SM-5 coverage signal is the payload) |

This roadmap is the phase model (`docs/phases.md`) **operationalized into a
tool**.

---

## The headline — the planning substrate for test generation

In 2026 anyone can ask a model to "write tests." The bottleneck is no longer
*generation* — it is **aim**. Ungrounded generation shotguns: it writes
plausible tests for code that was already covered and misses the error path
that mattered. Shadow Mirror is the **referential introspection layer that
tells the generator — human or model — exactly which semantic gaps to close.**

> The gap map *is* the prompt. Give a model "close these 5 resilient-level
> gaps on these specific nodes, here are the signatures and the uncovered
> branches," and ungrounded test-gen becomes targeted test-gen.

This is the product's center of gravity. Coverage mapping (the map) earns
trust; test planning (the plan) delivers value; **grounded generation (the map
as a generation substrate) is the headline that makes SM preferred over both
`pytest-cov` and ungrounded AI test-gen.** Every phase aims here.

---

## North-Star moments (define them now; aim every phase at them)

**NS-1 — the human moment.** A developer opens a PR adding error handling to a
payment path. `pytest-cov` reports **96 %**, CI goes green. `sm map --diff`
reports the new `except` branches *execute* but carry **0 / 5** resilient-level
assertions, and emits a 5-item plan. The developer gains trust in `sm` because cov said "fine" and SM said "you tested none of the failure recovery paths."

**NS-2 — the agent moment (headline).** An AI agent is told "add tests for this
module." Ungrounded, it produces six tests that re-state already-covered happy
paths. Given SM's gap map as context, the *same* agent produces five tests that
close the exact functional/behavioral/resilient gaps SM identified — and `sm
map` confirms the gaps closed. The mirror displays measurable improvements from the shadow of the existing program.

---

## Standing constraints (laws, not preferences)

- **C1 — Consume, don't rebuild.** SM never reimplements measurement. It
  consumes `coverage.py` (line/branch), `mutmut`/`cosmic-ray` (mutation),
  `hypothesis` (property), `pytest-benchmark` (timing) as *signals*. SM explores
  the **referential model, the map, the plan, the generation substrate, and
  the surfaces** — nothing below them. Integration friction is a reason to
  write an adapter, never to fork a measurement tool.
- **C2 — Trust anchor.** SM's reported line % must match `coverage.py`
  *exactly*, asserted in CI. The moment a user suspects SM disagrees with the
  tool they already trust, adoption dies.
- **C3 — Additive onboarding.** SM works on an existing pytest suite with
  **zero test rewrites** and **zero required annotations**. Anything inferable
  is inferred; anything else degrades gracefully.
- **C4 — Pristine / standalone.** No external or internal project references in the
  shipped tool or docs. The methodology is understandable and adoptable on its own.
- **C5 — Grounded generation is measurable.** Any generation feature (P5) must
  be evaluated by the *same* coverage map it consumes: a grounded run must
  close more semantic gaps than an ungrounded baseline, demonstrated, not
  asserted.

---

## Assumptions (defaults; redirect by editing here)

- **A1** — One roadmap going forward (this file). *Locked: supersede.*
- **A2** — **Python-first.** Prove the entire wedge on pytest + coverage.py
  before any second language. *Locked.*
- **A3** — **Grounded generation is the headline**, pulled forward to P5 (was
  a deferred surface). *Locked.*

---

## P0 — Foundations

Folded from the retired extraction roadmap, plus the model freeze.

- [x] `README.md` describes the seven-phase loop (C4)
- [x] SM-0..SM-6 phase definitions canonicalized — `docs/phases.md`
- [x] **Packaged as a Claude Code plugin** (Layer 5 distribution): one-plugin
      marketplace (`.claude-plugin/marketplace.json`) shipping `plugin/` with a
      pristine SM-0..SM-6 skill, `/shadow-mirror` command, and validation
      subagent. `claude plugin validate` passes; License Apache-2.0
- [x] Pristine SM-0..SM-6 SKILL.md authored in-repo, version-tagged `0.1.0`
      (the "better than the original" extraction).
- [x] Repo published at `shadow-mirror`; GitHub install path
      verified end-to-end (`marketplace add` → `install` → components register)
- [x] Receipt format v1 frozen + versioned — `docs/receipt-format-v1.md`
      (8-field atomic record; maps/plans compose from it; unblocks SM-4)
- [x] Reference Python data model in this repo (`shadow_mirror.Phase`,
      `ReceiptV1`) as composable primitives — frozen, no deps, 18 conformance
      tests green (phase-count contract + canonical-spec-example round-trip)
- [x] "Trust refinery" SVG authored (none pre-existed), committed at
      `docs/trust-refinery.svg`, and embedded in README — the SM-0..SM-6 loop
      as a refinery purifying a claim into a trusted `ReceiptV1`
- [x] Constraints C1–C5 recorded as testable invariants — `docs/constraints.md`
      registry; **C4 enforced now** by `tests/test_constraints.py`, C1 partial
      (zero-runtime-deps), C2/C3/C5 mapped to the phase that makes them testable

---

## P1 — Rubric spike (PAPER, no engine code) — *validate the premise first*

The whole value proposition rests on one unproven assumption: that
**functional / behavioral / performant / resilient can be operationalized into
automatic signals** rather than collapsing into subjective vibes. Answer it
with the cheapest possible tool first.

- [x] Pick one real ~50-line module with an existing pytest test —
      `shadow_mirror/receipt.py` (dogfood; tests in `tests/test_receipt.py`)
- [x] **By hand**: build its operation tree; classify existing assertions into
      the four levels; produce the by-hand map — `docs/spikes/P1-rubric-spike.md`
- [x] Ask: *does it tell me something `coverage.py` does not?* — **yes**:
      3 mutation-confirmed behavioral gaps on lines `coverage.py` calls 100 %
      covered (incl. two inside `dict.get(k, default)` default arms it can't see)
- [x] Write **level rubric v0** — an operational signal per level (proposed
      below; the spike refined it with an `N/A` verdict applied **per node**):

  | Level | Operational signal (consumed, per C1) |
  |-------|----------------------------------------|
  | Functional  | ≥1 assertion on the node's output/return for representative inputs |
  | Behavioral  | mutation score on the node (`mutmut`) — are mutants killed? |
  | Performant  | ≥1 time/memory/IO bound on the node (`pytest-benchmark`/explicit) |
  | Resilient   | error/`except` branches both executed **and** asserted-upon (+ optional fault injection) |
  | *(strength, cross-level)* | property-based presence (`hypothesis`) raises confidence on functional+behavioral |

**Gate.** If the by-hand map does **not** beat `coverage.py` on this module,
**stop and rethink the levels** — do not proceed. P1 exists to kill the
project cheaply if the premise is wrong.

> **Gate result: PASS (proceed to P2).** On `receipt.py` (`coverage.py`: 96 %),
> the by-hand map surfaced 3 mutation-confirmed behavioral gaps + 2 reasoned
> resilient gaps that `coverage.py` reports as covered, and showed Performant is
> N/A here. The levels operationalize cleanly; behavioral ≈ mutation score was
> validated by hand. Full write-up: `docs/spikes/P1-rubric-spike.md`.

---

## P2 — Vertical slice to the wedge demo — *one level, end-to-end, shippable*

Do **not** build the whole engine. Build the thinnest path that produces NS-1
on a real module.

- [x] **Operation tree (minimal):** AST → error branches (`raise`/`except`)
      with line ranges — `shadow_mirror/tree.py`
- [x] **Node identity scheme decided** *(R1):* `<path>::<qualname>#<kind>:<ordinal>`
      (stable under reformatting/line shifts) + a `shape_hash` (sha256 of
      normalized AST) seeding P4 rename-tolerance — `tree.py`, `tests/test_tree.py`
- [x] **Ingest `coverage.py`** (subprocess, consume-don't-rebuild) and project
      executed lines onto branches — `shadow_mirror/_run.py`
- [x] **C2 parity test:** SM covered-line count == `coverage.py`, exact integer —
      `tests/test_engine.py::test_c2_line_parity_exact_integer`
- [x] **Resilient level only.** "Asserted" = mutate the branch (perturb literal /
      swap raised type), rerun the suite, a test dies — `shadow_mirror/mutate.py`,
      `resilient.py`. Verdicts: proven · gap-unasserted · gap-unexercised
- [x] **Gap report:** human table + JSON (`--json`), `--fail-on-gap` to gate CI —
      `shadow_mirror/cli.py` (`sm map`)
- [x] **`sm map`** reproduces NS-1 — see Success below

**Success.** `sm map` surfaces ≥1 error path `pytest-cov` reported as covered
and a reviewer agrees is unproven.

> **Result: MET.** On `receipt.py` (97.6 % line coverage) `sm map` flags
> `__post_init__#raise:1` (line 79) as `gap-unexercised` — the exact gap the P1
> spike found — while correctly calling the tested guard `proven`. The
> `resilient_demo` fixture proves the signal **discriminates**: two identical
> `except` handlers get opposite verdicts (`proven` vs `gap-unasserted`) purely
> on whether a test pins the recovery — the NS-1 case, at 90 % line coverage.
> The raise type-swap uses a `BaseException` sentinel, so it pins **custom /
> out-of-table** exception types too (regression-guarded by `validate_sku`).
> Engine restores every mutated file byte-for-byte.
>
> **Known limitations (carry into P3/P4):**
> - **Wall-clock.** Each mutant reruns the *whole* test target —
>   O(branches × mutants × suite). Fine for a handful of branches; a real
>   module needs **test selection** (run only the tests covering the branch),
>   which is exactly what coverage dynamic contexts buy — so contexts may earn
>   their place later for *selection*, not for the asserted signal.
> - **Residual unprovable shapes** (reported `no-signal`/unkillable, rare): a
>   bare `raise` re-raise, and a test that pins only `BaseException`.

---

## P3 — Broaden the engine — *all four levels, full tree, receipts*

- [x] Operation tree at **function granularity** with cyclomatic-complexity
      weighting per node — `tree.build_functions`. (Finer sub-nodes —
      nested-branch/comprehension/async — deferred, noted in `coverage-levels.md`.)
- [x] **Functional, Behavioral, Performant** levels with measurable signals —
      `map.py`. Behavioral uses a frozen internal operator set `S` (mutmut as a
      future backend; the *signal* is frozen, not the tool); performant detects a
      time/resource bound in covering tests. Per-node `n/a` verdict (P1 refinement).
- [x] **Test selection** (the P2 wall-clock fix): coverage **dynamic contexts** →
      per-node covering test ids → mutate a node, rerun only its tests — `_run.py`.
- [x] **SM-4 persistence:** map → `ReceiptV1` (phase SM-5), `evidence_ref =
      sha256(canonical map)`; repo-relative paths + sorted collections →
      reproducible byte-for-byte (`tests/test_map.py::test_receipt_reproducible_and_valid`).
- [x] **SM-5 coverage signal** is the canonical map object (per-node × per-level
      verdicts + complexity) — `map.CoverageMap`.
- [x] Rubric v1 frozen + documented — `docs/coverage-levels.md`, **after** the
      separation check (below).

**Success.** A full four-level map on a non-trivial module, persisted as a
verifiable receipt, reproducible across runs.

> **Result: MET.** `sm map ... --receipt` produces a four-level map +
> reproducible `ReceiptV1` (SM-5) on `receipt.py` and the `resilient_demo`
> fixture. The rubric was **not frozen until separation was demonstrated** (the
> advisor's gate): functional and behavioral mutate different sites and *can*
> carry independent verdicts on the same node — shown by construction on the
> fixture (`apply_discount`, `charge`). This proves the levels are **not the same
> measurement**; it does **not** claim a real-world divergence *rate* (the fixture
> is hand-built to split, and `receipt.py` had too few comparable nodes to
> measure one — deferred to P8's evidence base). Four levels kept. Positive
> controls hold: `line_total` (well-tested
> arithmetic) reads behavioral `proven` (no equivalent-mutant false gap);
> `slow_double` reads performant `proven` (time bound detected) while others are
> `n/a`. Discipline deferred: finer sub-nodes, and consuming `mutmut`/
> `pytest-benchmark`/`hypothesis` as external backends (internal operator set for
> now; the signal — not the tool — is frozen).

### Rubric v2 — Observable (SHIPPED)

A fifth level, **observable** — *is an emitted signal (log / metric / event)
asserted?* Operator: nullify each bare emit (`logger.info(...)` → `None`). Because
an emit's return value is unused, the nullification is **data-flow-preserving**,
so the only test that can die is one that *observes* the emission — the cleanest
of the signals (no equivalent-mutant ambiguity). On `observable_demo` it
discriminates all four verdicts in one run:

| node | observable | why |
|---|---|---|
| `record_purchase` | `proven` | a `caplog` test asserts the emit |
| `compute_tax` | `gap-unasserted` | emit runs, covered, unobserved |
| `escalate` | `gap-unexercised` | emit line never runs |
| `add` | `n/a` | no emit |

- [x] Operator + site-lines in `shadow_mirror/mutate.py`
      (`make_observable_mutants` / `observable_site_lines`), gated to skip emits
      with side-effecting args (sound lower bound, no false `proven`).
- [x] `observable` wired into `map.LEVELS` and `build_full_map`; in-suite
      discrimination test (`tests/test_map.py::test_observable_discriminates`).
- [x] Maps stamp a top-level `rubric_version: 2`; the v1 four-level definitions
      are byte-compatible (purely additive). Receipt **wire format** stays
      `schema_version: 1`.
- [x] `docs/coverage-levels.md` → rubric v2 (v1 preserved + versioning note);
      README example regenerated from a real run; spike now imports from the
      package (no duplicate implementation).

**Deferred to v2.x — resolved.** Of the original deferrals, three shipped and two
were settled as soundness-declines (below); two sound-but-unbuilt features moved
to "Pending demand."

- [x] **Across-site worst-first aggregation** for functional / behavioral /
      observable (was: any-killed pooling — one pinned site read the whole node
      `proven`). Now each site is gated and scored independently; the node takes
      its worst site. Measured before/after: `orders.py` / `receipt.py` /
      `observable_demo` byte-identical (their multi-site nodes are homogeneous);
      the new `aggregation_demo` control flips `combine/behavioral` → `gap-
      unasserted` and `halves/functional` → `gap-unexercised`. The semantics
      changed even though those fixtures don't exercise it.
- [x] **Within-branch resilient leniency** closed. Resilient is now all-must-die
      within a branch too (every mutant must die), made sound by excluding string
      literals from mutation (`mutate._significant_consts`): a message string is
      not a gap, a non-string constant (`503`) is. Measured: `orders.py` /
      `receipt.py` / `observable_demo` byte-identical; the new
      `resilient_strict_demo` control flips `http_guard/resilient` → `gap-
      unasserted` (503 unasserted) while `require/resilient` stays `proven`
      (message-only). Both the map path and the P2 `resilient.py` path updated.
- [x] **Receiver-type emit detection — decided: soundness-decline.** Detecting
      "is this receiver a `logging.Logger`" statically needs type inference that
      dynamic Python doesn't give us; the logger-*name* heuristic is the sound
      lower bound (it misses an oddly-named logger — the safe direction). A
      receiver-type *guess* would risk labeling a non-logger call an emit (a false
      signal). The sound form is opt-in config, not inference — see "Pending
      demand."
- [x] **Significant-string detection — decided: soundness-decline.** The resilient
      string-exclusion is sound because *"a string literal in a raise is a
      message"* is a clean convention. *"This string is a significant code"* is not
      a convention but a guess: every static classifier misfires both ways
      (`"FATAL"` is an all-caps message; `"rate_limited"` is a lowercase code), and
      a message mislabeled as a code reintroduces the very message false-gap we
      excluded strings to kill. The lower-bound cost is **real, not cosmetic** —
      pinning an error *code* is legitimate contract-testing, unlike pinning
      message prose — so the sound fix is opt-in annotation (see "Pending
      demand"), never a heuristic.
- [x] **Behavioral equivalent-mutant symmetry — decided: do NOT exclude.**
      Behavioral stays a documented lower bound; it does not mirror resilient's
      exclusion. The coherence rule (one rule, not two trades): *exclude a
      mutation source only when domain convention says it carries no contract by
      default* — an exception message qualifies, an operator's result never does.
      And no behavioral exclusion is statically safe anyway: `*1→/1` changes
      `int`→`float`, `//1→*1` changes floor/sign, `+0→-0` breaks on signed zero —
      each killable, so excluding risks false `proven`. Measured by
      `behavioral_equiv_demo` (`scale_loose` gap-unasserted vs `scale_strict`
      proven on the same `* 1`); documented in `coverage-levels.md`
      ("Equivalent mutants — exclude by convention, never by guesswork").

**Pending demand** — sound and buildable, deferred until a real consumer (not
declined). These share one shape: the principled form of each is **opt-in user
configuration, never a heuristic** — the same conclusion the two declines above
reached.

- [ ] **Configurable emit surface** — let a project declare its emit method set
      (`statsd.incr`, OTEL spans, a custom `emit()`) beyond stdlib `logging`.
      Purely additive and sound; lacks a consumer (the CLI exposes no config yet).
- [ ] **Arg-preserving level-swap operator** — `info`→`debug` pins the *visibility
      level* (not just "emitted at all") and preserves argument evaluation. A
      sound additional observable signal; deferred pending demand.
- [ ] **Opt-in significance annotation** — the sound form of the two declines: a
      project marks which raised strings are contract (error codes) and which
      receivers/methods are emits. Configuration the author owns, not inference the
      tool guesses.

---

## P4 — Test planning (forward) + diff-aware

- [x] **`sm plan <target>`** → ranked (node, level) gaps + scaffolded assertion
      stubs (`shadow_mirror/plan.py`, built clean in the package — not by reusing
      the plugin's earlier heuristic scaffold, since retired). Pure post-processing over the
      map; deterministic. Stubs are **honest scaffolds** — real signature +
      level proof-obligation + `<PLACEHOLDER>`, never a fabricated oracle (which
      would poison P5). Raise-branches → `pytest.raises(RealExc)`; except-recovery
      branches → `assert call == <RECOVERED>`.
- [x] **Ranking** — transparent lexicographic sort over surfaced factors
      (complexity, then semantic-coverage *deficit* = gap levels / applicable
      levels, then verdict as a visible tiebreak), not an opaque score. The
      *changed-in-diff* factor lands with `--diff` below. Quality (are the top
      items genuinely missing?) is validated by dogfooding, not a self-confirming
      fixture; tests cover mechanics (determinism, tie-break, stub shape) only.
- [x] **Plan serializes as the front-half receipt** — `Plan.to_receipt` →
      phase `SM-2`, `outcome="inconclusive"` (predicates proposed, not yet run),
      `evidence_ref` carries the source map's ref as provenance.
- [x] **`sm plan --diff <base>`** → plan scoped to a PR's changed nodes.
      `shadow_mirror/_diff.py` parses `git diff --unified=0 <base>` to new-side
      changed lines (pure parser, unit-tested; git path slow-tested in a throwaway
      repo); `build_plan` filters to nodes whose `[lineno, end_lineno]` intersects
      them. Realizes the *changed-in-diff* factor as a **scope** (the
      complexity→deficit→verdict order applies within it). `diff_base` is recorded
      in the plan + receipt; non-diff `evidence_ref`s stay byte-identical (the key
      is omitted when absent). R1: maps current-tree lines to current-tree nodes
      via the stable qualname id — self-consistent; cross-version shape_hash
      rename-tolerance remains for historical-map comparison (P5+).

**Success.** On a real PR, `sm plan --diff` produces a plan whose top items a
maintainer agrees are genuinely missing. *Mechanics shipped; the maintainer-
agreement bar is validated in P8 dogfooding (needs a real external repo).*

---

## P5 — Grounded generation (HEADLINE) — *the gap map as a generation substrate*

The plan is not just for humans to read; it is **machine-consumable context
for a generator.** This is the product's headline (A3) and is gated on P4's
plan being good — a bad map produces bad prompts.

### Increment 1 — the verified primitives *(done)*

The headline rests on one claim that must hold: a generated test that *says* it
closes a gap actually does. Increment 1 builds the substrate + the
machine-checkable acceptance contract that proves the claim — so the comparative
eval (increment 2) measures grounding, not laundered broken tests.

- [x] **Closure primitive** — `shadow_mirror.closure.check_closure`: append a
      candidate to the suite, re-map the targeted cell, return
      `ClosureResult{valid, closed, regressions}`. Legitimate closure =
      `valid and closed and not regressions`.
- [x] **Green-gate is the centerpiece.** `build_full_map` reads only coverage
      contexts + mutation kills — *never* pytest's exit code — so a **red** test
      (fails on the unmutated module) reads as "always killed" and vacuously
      "closes" every gap. The closure primitive checks green *explicitly* first,
      and gates the **whole combined suite** — so it rejects both a red candidate
      *and* a candidate that breaks a sibling test via a module-level side effect
      (where coverage persists but the assertion fails). Without this the NS-2
      comparison inverts — an ungrounded baseline's plausible-but-red tests win.
      (`test_red_candidate_is_invalid`,
      `test_candidate_breaking_a_sibling_via_global_is_not_legitimate`.)
- [x] **Two complementary guards.** The green-gate catches a candidate that breaks
      a test's *assertion* (coverage persists); the **regression guard** catches one
      that drops a previously-proven cell's *coverage* — e.g. a candidate test that
      shadows a same-named proving suite test (Python keeps the last `def`).
      Precondition: the suite was green before (the map can't attest exit codes).
- [x] **Gap-map export** (`shadow_mirror.brief.build_brief`): per gap, the node
      signature, level + why, the assertion stub, and the **level proof
      obligation** (which mutation the test must make fail) — everything a
      generator needs to aim. Provenance chain `map_ref → plan_ref → brief_ref`.
- [x] **Provider-agnostic prompt contract** (C4): `GenerationBrief.to_prompt()` +
      the `ACCEPTANCE` contract — a schema + prompt, no vendor binding, no
      fabricated oracle. Surfaced as `sm plan --brief`.

### Increment 2 — the agent-integration loop *(done)*

The vendor-free realization of the headline. An `sm generate` that embedded a
model would bind a vendor and break C1/C4 in the runtime — so the **documented
agent integration** is the *right* form, not a fallback: the brief is the prompt,
an agent writes tests, `sm verify` is the mechanical acceptance gate.

- [x] **`sm verify`** (`shadow_mirror.verify`): a proposals manifest
      `[{node_id, level, candidate, label?}]` → each candidate checked
      independently against the baseline via `check_closure`; only legitimate
      closures are accepted. Targets validated up front (clean `unknown-target` /
      `not-a-gap` reasons, not a raised error). SM-5 receipt with `map_ref`
      provenance; exit 1 unless every proposal lands.
- [x] **Joint-safety gate.** Independent acceptance does *not* certify the set is
      jointly safe — two candidates can each close their target yet collide (a
      shared global, two same-named tests). When ≥2 are accepted, one final gate
      appends them all and re-maps once: `joint.safe` = all targets still proven +
      nothing regressed. (`test_verify.py::test_joint_unsafe_collision` — the
      analog of the green-gate dual.)
- [x] **Human-in-the-loop by default:** tests are *proposed*, the closure verdict
      is the acceptance gate, never auto-merge.
- [x] **Demonstration** (`docs/examples/grounded-loop.md`): a real round-trip —
      four briefed gaps closed, one deliberately-wrong test honestly rejected,
      the accepted set joint-checked. Labeled a demonstration, not the NS-2 claim.

**Deferred:**

- [ ] **C5 closed-loop eval (NS-2):** grounded vs ungrounded baseline, same
      model + module; grounded must close measurably more semantic gaps —
      **P8** (needs a real model + external repo)
- [ ] **Generator-callable loop** (`propose_and_verify(generator)`): the in-process
      SDK shape — deferred until the real generator interface is known (batch?
      retry? temperature sweep?), so P8's NS-2 harness isn't built on a guess
- [ ] Resilient **branch granularity** in the brief: requires the *map* to surface
      per-branch resilient verdicts first (today it's a single worst-first
      aggregate) — a map change, lowest value / highest coupling

**Status — P5 closed.** The headline loop is complete and demonstrated end to
end: `sm map` → `sm plan --brief` → an agent writes tests → `sm verify`. Every
closure is *mechanically proven* against the real code (green-gated, regression-
guarded, joint-checked), so grounded generation can never launder a broken test
into a green checkmark — the property the headline rests on. C5 is satisfied as a
**mechanism**: acceptance is measured by the same map, by construction.

The one thing P5 does *not* close is the comparative **measurement** — that a
grounded run beats an ungrounded baseline on a real model and a real repo. That is
NS-2, and it is the single P5-originated item carried to **P8** (with the
generator-callable SDK loop it will define). The mechanism is done; the benchmark
is dogfooding.

**Success (the P8 bar).** The NS-2 head-to-head is real and repeatable: same
model, same module, grounded run measurably closes gaps the ungrounded run leaves
open.

---

## P6 — Surfaces — *where developers and agents already live*

- [x] CLI: `sm map`, `sm plan`, `sm verify`, `sm delta`, `--json`, gating exit
      codes (`--fail-on-gap`, `--fail-on-regression`, `--gate-complexity`). The
      listed `sm generate` is the deferred agent-callable loop (P8); the documented
      agent integration is `sm plan --brief` → agent → `sm verify` (P5).
- [x] **Semantic-coverage delta** (`shadow_mirror/delta.py`, `sm delta`): compare a
      base vs head map (two `sm map --json` payloads) → `closed` / `regressed` /
      `new_gaps`, with `base_ref`/`head_ref` provenance. The engine the next two
      bullets sit on.
- [x] **Optional gate** — `sm delta --fail-on-regression` blocks a PR that drops a
      proven cell to a gap; `--gate-complexity N` also blocks a *new* gap on a
      node of complexity ≥ N. Off by default (C3).
- [x] **CI / PR annotation:** `sm delta --markdown` emits a PR-comment-ready delta
      (regressions first) with a hidden marker for a **sticky** find-and-update
      comment (no per-push spam). A copy-and-adapt GitHub Action wires it up:
      `docs/examples/github-action.yml`. *The CLI rendering is tested and supported;
      the workflow YAML is an **unverified template** (shipped in docs/, not a live
      `.github/workflows/` file) — the comment-id lookup in particular is
      illustrative and should be confirmed against the consumer's `gh` version.*
- [x] **HTML map view** (`shadow_mirror/html.py`, `sm map --html PATH`): a
      standalone, dependency-free HTML page (inline CSS, color-coded cells, gaps
      highlighted, escaped names, no embedded timestamp → deterministic). The
      "trust refinery" *SVG* already ships as a static asset (`docs/trust-refinery.svg`),
      so this bullet is HTML only.
- [x] **MCP / agent endpoint** (`shadow_mirror/mcp_server.py`, `sm-mcp`): a stdio
      server exposing `sm_map`/`sm_plan`/`sm_brief`/`sm_verify`/`sm_delta`. The `mcp`
      SDK is an optional `[mcp]` extra; the handlers (`mcp_tools`, no `mcp` import)
      are split from the wiring, so the core stays dependency-free — C1, guarded by
      `test_c1_importing_package_does_not_pull_mcp`. `sm_verify` takes candidate
      source inline; every engine-running tool anchors the process cwd to the caller's
      `cwd` (the dogfooding-surfaced resolution trap).
- [x] **Runtime logging** (`sm -v/-vv`): a tool about observability made observable —
      `-v` logs per-node verdict rows, `-vv` every mutant (site/branch → killed /
      survived) as it runs. stdlib logging, silent unless the CLI attaches a handler.
- [x] **Container demo (Rung 1)** — `docker/Dockerfile` + `.devcontainer/` + a tiny
      sample (`examples/sample-repo/`) running `sm map -vv` / `sm plan` and **mutmut**
      side by side, contrasting the semantic-level map with a flat mutation score
      (honestly — neither is a strict superset). The engine installs from local
      source (no PyPI/git auth). The OCI image is the canonical runs-anywhere surface.
      *Verified end-to-end (`docker build` + `docker run`): in the pinned 3.12 base
      mutmut runs clean and reports 11 survivors — all in `apply_markup` + `withdraw`,
      the exact two functions `sm` flags as gaps — corroborating the honest contrast.*
    - **Rung 2 (browsers)** — the base image is a swappable `ARG` defaulting to slim,
      documented to point at a trusted Playwright image; *deferred* (mapping UI-level
      "proven" is an open design question, and the Helm/custom-image option is future).
    - **Rung 3 (eBPF/Cilium meta-telemetry)** — *deferred*; lives in the
      container/simulator space and is progressing elsewhere.

**Success.** A PR shows an inline Shadow Mirror semantic-coverage delta + plan
a reviewer uses; an agent can fetch the gap map programmatically. *Both shipped:
the delta + `--markdown` + the copy-and-adapt Action cover the PR surface; `sm-mcp`
covers the agent surface. The only remaining P6 item is the live GitHub Action,
which is the consumer's to enable from the template.*

**Status — P6 closed.** Shadow Mirror now meets developers and agents where they
work: `sm delta` (+ `--markdown` + the opt-in regression/complexity gate) and the
copy-and-adapt Action for PR review; `sm map --html` for a standalone visual; and
`sm-mcp` exposing `map`/`plan`/`brief`/`verify`/`bundle`/`delta` (multi-language via
a `language` param) to an agent host — all without adding a runtime dependency to
the core (C1 held; the MCP SDK is an opt-in extra, guarded by a test). What P6 does
*not* include is a live GitHub Action in this repo (shipped as a docs template —
unverified by design) or the in-the-loop NS-2 measurement (that needs a real model +
repo → P8). Surfaces are done; the proof at scale is dogfooding.

### Containerized MCP runtime (cloud) — deferred (trigger: cloud testing / untrusted targets)

The `sm-mcp` stdio server runs a venv python directly today (`plugin/.mcp.json` →
`${CLAUDE_PLUGIN_DATA}/mcp-venv/bin/python -m shadow_mirror.mcp_server`) — the right
default for a **trusted** visit (known targets, local). Two pulls make a container
the right runtime: **cloud testing** (a runs-anywhere image) and **untrusted
targets** (the engine *executes the target's tests* — overlaying mutated source and
spawning `coverage`/`vitest` subprocesses against arbitrary code — so the target
needs an isolation boundary). MCP is stdio either way, so this is a *deployment*
swap, not a tool-code change. Distinct from the P6 `docker/` **demo** image
(sm-vs-mutmut contrast); this is the **server** image.

- [ ] **Two-toolchain server image** — one OCI image carrying *both* engine
      runtimes: python + coverage.py AND node + vitest + the tree-sitter grammars
      (`.[engine,js,ts,mcp]` + `npm`), so one container serves python/js/ts/tsx maps.
- [ ] **`.mcp.json` command swap** — point `command` at a container runtime
      (`docker`/`podman run -i … sm-mcp`) wrapping the same stdio server; keep the
      venv runner as the trusted-local default (opt-in per host, not a forced change).
- [ ] **Mount contract** — the target project bind-mounts in **read+write** (the
      engine overlays mutated files and runs the suite in place); document the bind,
      the cwd anchoring (`mcp_tools._at`), and that the image must NOT bake the target.
- [ ] **Sandbox boundary** (the isolation rationale) — resource limits
      (cpu/mem/pids — the engine fans out subprocesses), no-network-by-default for a
      run, read-only root + writable target mount, non-root user. This is what makes
      an *untrusted*-target visit safe.
- [ ] **Multi-arch publish** — build + push `linux/amd64,linux/arm64` to a registry
      for cloud pulls; pin base + lockfiles, and record the **image digest in the
      receipt `instrumentation`** so a cloud-produced EvidenceBundle is provenanced
      to the exact runtime.
- [ ] **Cloud test harness** — run `sm_map`/`sm_bundle` against a cloned repo in the
      cloud; the self-verifying **EvidenceBundle** is the portable result (verifies
      across the boundary). Ties into P8's "living demos in CI."

---

## P7 — Multi-language (the second ecosystem) — *one engine, four languages*

JS/TS chosen as the second ecosystem (tree-sitter parse · Istanbul coverage ·
vitest runner). **Eight** de-risking spikes (`docs/spikes/P7-*.md`) measured — not
assumed — that all five levels + coverage attribution + the join/selection loop
port; each cleared one capability and guarded one silent-correctness trap. The
slice then shipped **four** languages behind one SPI — Python, JavaScript,
TypeScript, TSX — all conformant to the same Python ground truth.

- [x] **Adapter SPI** — `shadow_mirror/spi.py`: the `LanguageAdapter` Protocol +
      core-owned cross-boundary types, the three spike invariants (full-span
      `executed_lines`; well-formed-only `mutants`; selection-addressable `TestId`)
      encoded as contract, node-identity + shape-hash core-specified so receipts stay
      cross-language comparable. Later gained `toolchain()` (provenance, below).
- [x] **PythonAdapter** — extracted the tree.py/mutate.py/_run.py/map.py functions
      behind the SPI; `build_full_map` routes through a `LanguageAdapter` (default
      Python). Validated **byte-identical** (4 fixtures × 5 levels) — the SPI's
      well-shapedness proof — and removed two pre-SPI hacks in the process.
- [x] **JsAdapter** — the SPI on tree-sitter + Istanbul + vitest. `tests/
      test_conformance_js.py` asserts JS verdicts == Python GROUND TRUTH, keyed on
      (qualname-correspondence, level); skips without the toolchain, **hard-fails
      under `SM_REQUIRE_JS=1`** in CI (the gate is enforced, not green-with-skips).
- [x] **TsAdapter** — TypeScript via a grammar-parameterized shared
      `_TreeSitterAdapter` base. The one seam — Istanbul's source-map round-trip on
      transpiled TS — was spiked clear (`P7-typescript-spike.md`); conformance mirrors
      orders + service across all five levels.
- [x] **TsxAdapter** — `.tsx`/JSX. Spiked (`P7-tsx-jsx-spike.md`): logic ports under
      the identical line-join; the gate was a runtime seam, shipped as two slices —
      **(1)** `coverage()` *inherits* the target's vitest config (`mergeConfig`, so a
      DOM `environment`/`setupFiles`/`esbuild` jsx survive instead of being replaced)
      and **(2)** the `language_tsx` binding + a Preact component-render fixture
      (proven/gap discrimination on a JSX-embedded site). Kept separate from
      TsAdapter (the `<T>` cast vs JSX grammar collision).
- [x] **Same operation-tree + receipt model, four languages, one conformance suite**
      (37 tests green). Reachable, not library-only: the CLI (`--lang`) and the MCP
      server (a `language` param) expose the multi-language engine.
- [x] **Real provenance** — adapter `toolchain()` makes the receipt's
      `instrumentation` version-stamped + language-correct (a JS receipt no longer
      claims `coverage.py`); **EvidenceBundle** (`docs/evidence-bundle.md`,
      `sm map --bundle` / `sm_bundle`) embeds the canonical map alongside the receipt,
      self-verifying (`verified ⇔ sha256(evidence) == receipt.evidence_ref`).

**Resolved provisionals** (each measured, not assumed): TS source-maps → **built**
(TsAdapter, seam spiked clear); async `rejects.toThrow` → **built** (zero operator
code — an async throw is the same `throw_statement`; a conformance row added);
operation-tree construction from tree-sitter → **closed as a non-item** (the engine's
op-tree *is* `ModuleModel` from `discover()`; no separate capability to build); JS
instanceof-routing → **deferred with reason** (Python's resilient level has no
error-type-routing operator, so adding one would make JS stricter than Python and
break cross-language identity — a rubric decision, not a port); vitest-`bench` →
**deferred, architectural** (errors under `vitest run`, no per-test coverage, can't
attribute per-node).

**Success.** Identical map/receipt/gap-map semantics across languages. **MET** —
Python ≡ JS ≡ TS ≡ TSX, anchored to one Python ground truth, CI-green on 3.10/3.12.

**Status — P7 closed.** One SPI, four languages, one conformance suite. The
multi-language engine is reachable through the CLI (`--lang`) and the MCP server (a
`language` param + the `sm_bundle` tool), with language-correct provenance in every
receipt and a standalone self-verifying EvidenceBundle as the portable result.
Remaining tails are small and flagged in their spikes: `.d.ts`/decorators and
expression-bodied arrow components (no functional site, lower-bound); the
configurable emit surface / level-swap operator (P3 "Pending demand"); and the
cloud/container runtime (P6 deferred).

---

## P8 — "Preferred" certification

The North-Star moments, proven at scale. Includes the retired roadmap's
example + release gates.

> **Dogfooding slice (one external repo, two modules) — run before P6.** It
> confirmed **C2 line parity on real code** (exact integer counts matched
> `coverage.py`) and reproduced an **NS-1**: a covered, output-asserted function
> whose behavioral logic a surviving operator-mutation showed unpinned — green to
> line coverage, a gap to `sm`. It also surfaced the in-place-mutation
> crash/concurrency hardening now shipped. Two open notes from it:
>
> - **Mapping needs the target's test env.** `sm map` runs the target's *own*
>   suite under coverage, so collecting even a single leaf module imports its
>   package `__init__` and needs the project's full dependency tree installed —
>   the same prerequisite as running its tests, not a defect. Document it in
>   onboarding (C3: "install your test deps first"), and consider emitting a clear
>   error when a target import fails for a missing dependency rather than a raw
>   traceback.
> - **`module`-key relpath portability** — confirmed observable (the real module
>   mapped with a bare relpath key). Already tracked under *Cross-machine
>   reproducibility* below; the slice is the empirical confirmation.

- [ ] Dogfood on ≥3 real external projects; each surfaces a real gap
      `pytest-cov` hid (NS-1)
- [ ] **`sm map --tests <dir>` (whole-suite credit)** — today `--tests` is
      single-file by design. Two layers assume a file: `_timing_test_funcs`
      (`map.py`) `ast.parse(read_text())`s the path (→ `IsADirectoryError` on a
      dir), and `_ctx_to_nodeid` (`_run.py`) rebuilds covering-test nodeids as
      `f"{tests_path}::{name}"` — coverage's dynamic context carries only
      `module.func`, not the file, so a dir yields malformed `tests/::test_x`
      ids and per-mutant selection silently breaks (every map reads all-gaps).
      Needs a real `module→file` resolver across `_ctx_to_nodeid`,
      `run_coverage_with_contexts`, and `_timing_test_funcs`. Surfaced
      2026-06-07 trying to compute an honest full-suite semantic self-map
      (line+branch self-coverage was 89%; suite 200/200). Any mutation sweep
      should run in a throwaway `git worktree`/clone — `sm map` rewrites
      sources in place and a kill mid-mutant corrupts the primary checkout.
- [x] **Behavioral false-negative on multi-line-call continuation lines — FIXED.**
      A behavioral mutation site whose operator sat on a *continuation line* of a
      multi-line call (e.g. `a == b` as an argument inside a `Foo(\n …,\n)` call)
      read `gap-unexercised` even when the suite exercised it every run.
      `coverage.py` attributes execution to the statement-start line, not the inner
      argument line, so the operator's `lineno` was absent from `executed_lines`;
      `_site_verdict` (`map.py:189`) gated it out *before* any mutant ran, and
      `_level_verdict`'s worst-first `min` (`:214`) sank the whole node even when
      every sibling site was `proven` — an **un-closable-by-tests** cell.
      Under-reported, never over-reported. Surfaced 2026-06-09 via reciprocal
      feedback (`incoming/2026-06-09-sm-feedback-multiline-check-blindspot.md`).
      **Resolution:** the bug was an *unimplemented invariant* — `Coverage`
      (`spi.py`) documents `executed_lines` as full start..end span-expanded, but
      the adapter passed coverage.py's raw start-line-only set straight through.
      Implemented `adapters/python.py::_expand_executed_lines`: a statement whose
      *own* lines (full span MINUS every nested statement's span) executed
      contributes its whole range — so a multi-line call's continuation operators
      are attributed, while an executed compound-statement header never drags in an
      unexecuted body (no false `gap-unasserted`). Line% (C2) is untouched (only the
      gate set expands). The `verify.py` repro flips `gap-unexercised → proven`;
      true-negative + compound-body cases pinned (`tests/test_spi_python_adapter.py`),
      full suite 205 green.
- [ ] **Evidence base** — measure the functional/behavioral divergence *rate* on
      ≥1 non-trivial real module (P3 only demonstrated it is *representable* on a
      hand-built fixture, not a rate). Confirms the four-level split earns its
      keep on real code, not just by construction.
- [ ] **Cross-machine reproducibility** — the map's `module` key is a
      relpath-from-`cwd`, so `evidence_ref` is only stable for a fixed layout
      (**confirmed observable** in the dogfooding-slice note above). Decide whether
      receipts must be byte-identical across checkouts/machines (e.g. normalize to
      a repo-root-relative path) before the v1 receipt is certified portable.
- [ ] The canonical examples run in CI as living demos on tagged releases:
      unit test · integration test with eBPF instrumentation · Playwright UI
      test · a state-machine status transition (e.g. draft → confirmed loop)
- [ ] NS-2 grounded-vs-ungrounded eval published as a reproducible benchmark —
      builds on P5's `sm verify` acceptance gate; defines the generator-callable
      loop (`propose_and_verify(generator)`) deferred from P5 increment 2
- [ ] Onboarding < 5 min on an existing pytest project, zero rewrites (C3)
- [ ] C2 line-% parity green across all dogfood projects
- [ ] One non-author developer reaches for `sm` to make a real test decision
      without being prompted
- [ ] Receipt format v1 has ≥1 external implementation that verifies receipts
      produced by the reference implementation
- [ ] Docs review: the seven phases described with no reference to any other
      project, internal or external (C4)
- [ ] Tagged release v0.2.0 (semver commitment); PyPI publication; Swift
      Package Index registration

---

## Interop — cross-validation with other instruments (deferred / parked)

Shadow Mirror can act as one instrument in a neutral cross-validation against
others. A 2026-06 read-only exchange of review reports (staged in `incoming/`,
gitignored) with a sibling trace-lineage instrument produced exactly one refined
item — no new features (the sibling's review found SM already ships what it
praised), but two shaping findings:

- [ ] **Any verdict projection must preserve proof-strength.** A neutral "verdict
      view" of an SM bundle must NOT flatten `proven` (mutation-verified, per
      level) into a bare `attested`/`passed` bit — that would bake in the exact
      "schema-shaped but not measured" gap SM exists to expose. Carry an explicit
      basis/strength marker; emit honest **degenerate** values for anything SM did
      not measure (e.g. a trace topology SM has no source for ⇒ 0 spans), never
      fabricated ones. (The verdict-level restatement of "never claim *proven* for
      merely *executed*.")
- [ ] **The reciprocal "install each plugin in the other's session" cross-check is
      *parked*, not merely gated.** SM and a trace-lineage instrument correspond on
      only one axis (attestation), and SM records zero trace spans — so there is no
      honest cross-check *beyond* attestation until SM grows a locational/topology
      dimension. Until then, report-exchange (advice → `incoming/` → roadmap) is the
      right integration level.
- The bridge itself lives **outside** the shipped core (C4) — a neutral harness
  owned by neither project, never in `shadow_mirror/`. Distilled, name-free items
  graduate here; the name-bearing source reports stay in gitignored `incoming/`.

---

## Cross-cutting risks (designed for, not discovered)

- **R1 — Node identity stability.** If renaming a function or adding a branch
  shifts node IDs, the historical map and *all* diff-aware planning (P4) and
  grounded generation (P5) silently break. **Decided in P2, hardened in P4.**
  Likely scheme: qualified-name primary key + normalized control-flow-shape
  hash as rename-tolerant fallback.
- **R2 — Level subjectivity.** The levels are the whole point; untied to
  *measurable* signals (P1 rubric) they become a taste score nobody trusts.
  The P1 gate kills the project if they can't be grounded.
- **R3 — Ungrounded generation contaminates the headline.** If P5 ships before
  P4's plan is trustworthy, SM-grounded generation is no better than shotgun
  generation and the headline collapses. P5 is gated on P4; C5 is the proof.
- **R4 — Adoption friction erodes C1/C3.** The pull to "just compute it
  ourselves" or "ask the user to annotate" is constant and forbidden;
  deviations require an explicit, documented exception.
- **R5 — Scope.** Mapping + five levels + planning + generation + multi-language
  at once = nothing ships. The vertical slice (P2) is the antidote: one level,
  one language, end-to-end, *first*.
