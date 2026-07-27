# Coverage levels — rubric v2

Shadow Mirror scores each function node on five **levels**. A level is not a
percentage; it is a **verdict per (node, level) cell**. This document freezes the
operational signal for each level and the verdict rules.

## Rubric versioning

Every map stamps a `rubric_version` into its canonical JSON (so a consumer never
infers the level set by counting cells):

- **v1** — four levels: functional, behavioral, performant, resilient. Frozen
  after the engine was built and the functional/behavioral separation was
  *measured* (see "Why the levels are distinct"). A receipt carrying
  `rubric_version: 1` is read under these four definitions; they are **unchanged**
  in v2.
- **v2** *(current)* — adds **observable** as a fifth level. Purely additive: the
  four v1 definitions are byte-compatible, so a v2 map is a v1 map plus one cell
  per node. Adding the cell changes a node's `evidence_ref`, which is why it is a
  version bump rather than a v1 patch.

## Verdicts

| Verdict | Meaning |
|---------|---------|
| `proven` | a test pins this level for this node |
| `gap-unasserted` | the code runs, but nothing would notice if this level were broken |
| `gap-unexercised` | the relevant code never runs under the suite (coverage.py already sees this) |
| `n/a` | this level does not apply to this node (per-node, not a 0%) |
| `no-signal` | the node ran but no covering test could be resolved (an error state, **not** a gap) |

## The five levels

| Level | Signal (consume, don't rebuild) | `n/a` when | `proven` when |
|-------|----------------------------------|-----------|---------------|
| **functional** | mutate each `return <value>` → `return None`; rerun the node's covering tests | the node returns no value (side-effect-only) | a covering test dies — the output is observed |
| **behavioral** | swap one operator (arithmetic / comparison / boolean) per mutant; rerun covering tests | the node has no swappable operator | a covering test dies — the logic is pinned |
| **performant** | a covering test asserts a time/resource bound (a `benchmark` fixture or a `perf_counter`/`monotonic`/`process_time` reading) | no covering test asserts a bound | such a test exists |
| **resilient** | the P2 error-branch signal: mutate the `raise`/`except` (type-swap + non-string constant perturbs; message strings excluded), aggregated worst-first across branches and all-must-die within each | the node has no `raise`/`except` | every executed branch has every mutant killed |
| **observable** *(v2)* | nullify each bare emit (`logger.info(...)` → `None`); rerun covering tests | the node has no nullifiable emit | a covering test dies — the emitted signal is asserted |

"Executed?" comes from `coverage.py`. "A test dies?" comes from rerunning **only
the tests that cover the node** (coverage dynamic contexts → pytest nodeids), so
the cost is per-node, not whole-suite.

### Reference operator set `S` (behavioral)

Frozen, so the signal is "mutation survival under `S`", not "some tool's score":

- arithmetic: `+ ↔ -`, `* ↔ /`, `// → *`, `% → *`, `** → *`
- comparison: `== ↔ !=`, `< ↔ >=`, `> ↔ <=`, `is ↔ is not`, `in ↔ not in`
- boolean: `and ↔ or`
- functional: `return <value> → return None`
- observable: `<emit-statement> → None` (nullify a bare `logger.<method>(...)`)

A stronger external backend (`mutmut` / `cosmic-ray`) MAY replace `S` later; the
verdict semantics (a surviving mutant on a covered node ⇒ `gap`) stay fixed.

## Aggregation — per-site, worst-first

A level mutates one or more **sites** in a node (each `return`, each operator,
each emit). The node's verdict for that level is the **worst** of its per-site
verdicts, where each site is gated on *its own* line:

| site is… | site verdict |
|----------|--------------|
| never executed | `gap-unexercised` |
| executed, no covering test resolved | `no-signal` |
| executed + covered, its mutant survives | `gap-unasserted` |
| executed + covered, its mutant dies | `proven` |

Worst-first uses the verdict ordering `gap-unasserted` < `no-signal` <
`gap-unexercised` < `proven` < `n/a`. So a node with one pinned site and one
unpinned site is **not** `proven` — a surviving (or never-run) mutant on any site
is a gap. The `aggregation_demo` fixture is the control: `combine` (two operators,
only `*` asserted) reads `behavioral: gap-unasserted`; `halves` (two returns, the
second never run) reads `functional: gap-unexercised`.

**This corrects an earlier any-killed pooling** that read a node `proven` when a
*single* site was pinned, masking gaps on its other sites. Two notes on scope:

- **Existing fixtures don't flip.** Their multi-site nodes are homogeneous
  (`line_total` all-pinned, `apply_discount` all-unpinned, `normalize_qty`
  both-pinned), so `resilient_demo` / `receipt.py` / `observable_demo` verdicts —
  and their `evidence_ref`s — are byte-identical before and after. The semantics
  changed; those particular inputs don't exercise the change.
- **`evidence_ref` hazard.** Because the computation changed, a heterogeneous
  multi-site node can hash differently under the same `rubric_version: 2`. This
  correction landed in the same session v2 shipped (no persisted receipts existed
  to invalidate); it is specified here rather than version-bumped.
- **Resilient is all-must-die too** (across *and* within branches). A branch is
  `proven` only if every mutant on it dies; one survivor is `gap-unasserted`. This
  works because the equivalent-mutant problem is handled at mutation time:
  **string literals in a `raise`/`except` are not perturbed** (see
  `mutate._significant_consts`) — they are almost always the human-readable
  message, not behavior to assert. So `raise HttpError(503, "down")` pinned only
  by `pytest.raises(HttpError)` reads `gap-unasserted` (the `503` mutant survives
  — a real unasserted constant), while `raise ValueError("x required")` pinned by
  type reads `proven` (only the type-swap mutant exists; the message is never a
  gap). The `resilient_strict_demo` fixture is the control for both. A genuinely
  significant *string* (an error code like `"E1234"`) is the lower-bound cost: it
  is missed, never falsely flagged. Recovering it is **declined as a heuristic**:
  *"a string in a raise is a message"* is a clean convention, but *"this string is
  a code"* is a guess that misfires both ways (`"FATAL"` is a message,
  `"rate_limited"` is a code) and would reintroduce message false-gaps. The sound
  form is opt-in author annotation, not inference (`ROADMAP.md` → Pending demand).
  (An `except` whose only constant is a string now has
  no const mutant, so it falls back to the **blank-except** mutant — neutralizing
  the handler body — which pins the recovery by *behavior* not message text; see
  `lookup` in the control.)

## Equivalent mutants — exclude by convention, never by guesswork

Resilient excludes string-literal mutations; behavioral excludes nothing. That is
**one rule, not two ad-hoc trades**:

> Exclude a mutation source only when domain *convention* says it carries no
> behavioral contract by default. Otherwise keep it — a surviving mutant is at
> least a candidate gap.

An exception's **message string** qualifies: asserting exact error-message text is
a widely-held anti-pattern, so by convention the message is not part of the
contract, and a surviving message-perturbation is not a gap. An **operator's
result is the function's output** — there is no convention that "× 1 isn't part
of the contract," so an operator swap never qualifies. The principle is what makes
the two levels coherent: resilient accepts a tiny false-*negative* risk (a
significant string like `"E1234"` is missed) to avoid message false-*positives*;
behavioral refuses to trade in the other direction.

It refuses because the trade isn't even available: **there is no statically,
universally safe behavioral exclusion.** The swaps that *look* equivalent aren't:

- `x * 1 → x / 1` — `6 * 1` is `int 6`, `6 / 1` is `float 6.0` (type change).
- `x // 1 → x * 1` — `-7.5 // 1` is `-8.0` (floor), `-7.5 * 1` is `-7.5`.
- `x + 0 → x - 0` — breaks on signed zero: `-0.0 + 0` is `0.0`, `-0.0 - 0` is
  `-0.0` (distinguishable via `repr` / `copysign` / `1/x`).

Each is *killable* by a sufficiently strict test, so excluding it would risk a
false `proven` — hiding a real type/precision gap, the worse direction. The
`behavioral_equiv_demo` control measures this: `scale_loose` (`return x * 1`,
value-only test) reads `gap-unasserted` — the `*1→/1` mutant survives `6 == 6.0`;
`scale_strict` (same expression, type-pinning test) reads `proven` — the mutant
dies on `int` vs `float`. The same mutant, two verdicts: it is killable, not
equivalent. So **behavioral stays a documented lower bound** (a surviving swap is
*evidence of* a gap, possibly an equivalent mutant) rather than excluding sources
it cannot prove inert.

## Why the levels are distinct (the separation check)

The P1-style worry: functional and behavioral might be the *same* measurement
(both mutate the return expression, both die to the same value assertion). What
keeps them distinct is that they mutate **different sites** — functional rewrites
`return <value>`, behavioral swaps operators in the body — so a test can pin one
without the other.

That divergence is *constructible*, and the `resilient_demo` fixture is built to
exhibit it deliberately (so the rubric has a positive control):

- agree (`proven`/`proven`) when one strong value assertion pins both:
  `line_total`, `slow_double`.
- diverge by design: `apply_discount` (func `proven`, beha `gap-unasserted` —
  output observed via a weak `>= 0` test, logic not pinned); `charge`
  (func `gap-unexercised` — only the reject path is tested, so the `return` line
  never runs — beha `proven` — the guard comparison is pinned).

What this shows is **representability**, not a base rate: the two levels *can*
carry independent verdicts on the same node, which is the precondition for
keeping them separate. It does **not** establish how often real code diverges —
the fixture is hand-built to split, and the one real module checked so far
(`receipt.py`) had too few comparable nodes to measure a rate. Measuring the
real-world divergence rate on a non-trivial module is a deferred evidence-base
item (see `ROADMAP.md` P8). The levels are kept separate because they are not
the same measurement — not because of a measured agreement percentage.

**Observable** is distinct by construction — it mutates a site no other level
touches (a bare emit statement), and a node's emit verdict is independent of its
return/operator/error verdicts. The `observable_demo` fixture is the positive
control: `record_purchase` (`proven`), `compute_tax` (`gap-unasserted`),
`escalate` (`gap-unexercised`), `add` (`n/a`) exercise all four verdicts in one
map. Because nullifying an emit is data-flow-preserving, observable has **no
equivalent-mutant ambiguity** — unlike behavioral, a surviving observable mutant
is a true gap, not a possible one.

## Honest scoping (limitations)

- **Behavioral is a lower bound.** An operator swap can be a true *equivalent*
  mutant (no input distinguishes it) that survives without being a real gap, so a
  surviving behavioral mutant is *evidence of* a gap, not proof. We do **not**
  exclude such mutants — none is statically, universally safe to drop (see
  "Equivalent mutants — exclude by convention, never by guesswork"). Positive
  control: `line_total` reads `proven` (no false gap); `behavioral_equiv_demo`
  shows the same swap reading `gap-unasserted` vs `proven` under weaker/stronger
  tests.
- **Behavioral is `n/a` for operator-free code.** Dict/string/coercion code
  (e.g. all of `shadow_mirror/receipt.py`) has no swappable operators; behavioral
  contributes nothing there. Functional and resilient carry those nodes.
- **Performant has no automatic `gap`.** Declaring a node performance-sensitive
  needs intent we don't infer, so performant is `proven` (a bound is asserted) or
  `n/a` — never `gap`. It is detection-only.
- **Observable is a lower bound, and detection is a heuristic.** An emit is
  recognized as `<logger>.<method>(...)` — the method in `{debug, info, warning,
  warn, error, exception, critical, log}` **and** the receiver name logger-shaped
  (`log` / `logger` / `logging`, any underscore/case spelling). This is a name
  heuristic, **not** a type check: it deliberately skips a domain method named
  like a log level (`audit.log(x)`, `db.error(x)`) so a domain side effect is
  never mistaken for an observability assertion — but it also misses an
  unconventionally-named logger (the safe, lower-bound direction). Two further
  conservatisms: emits whose arguments contain a side-effecting call
  (`logger.info("x", f())`) are **skipped** (nullifying would drop `f()` too — a
  *false `proven`*); and only stdlib-`logging`-shaped calls are seen at all.
  Precise receiver-type detection, a configurable metrics/trace/custom-`emit()`
  surface, and the stronger `info → debug` **level-swap** operator (preserves
  args, pins the *visibility level*) are all deferred to v2.x.
- **Node granularity.** Nodes are functions; nested branches/comprehensions are
  not yet separate nodes (cyclomatic complexity is recorded per function as a
  weight). Async and finer sub-nodes are deferred.

## The map artifact

A map serializes to a content-addressable `ReceiptV1` (phase `SM-5`):
`evidence_ref = "sha256:" + sha256(canonical_map_json)`. The canonical JSON uses
repo-relative paths and sorted keys, and carries a top-level `rubric_version`, so
the hash is reproducible across runs and machines and self-describes its level
set. `outcome` is `verified` when there are zero gaps, else `inconclusive`. See
[receipt-format-v1.md](receipt-format-v1.md) — the receipt **wire format** stays
`schema_version: 1`; only the rubric (the level set inside the map) is v2.
