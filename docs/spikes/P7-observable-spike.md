# P7 — Observable level in JS (the fifth level; emit detection re-grounded)

**Question.** Observable is rubric-v2's fifth level: *is an emitted signal (log /
metric / event) asserted, or merely produced?* Python operationalizes it by
**nullifying a bare logging emit** (`logger.info(...)` → `None`) — the return is
unused, so the nullification is data-flow-preserving and the only test that can
die is one that asserts on the emitted signal (via `caplog`). The *mutation
mechanic* is just the already-proven functional `→null` splice. What does **not**
port for free is the **detection surface**: Python keys on stdlib `logging`
(`_EMIT_METHODS` × `_LOGGER_NAMES`), and **JS has no stdlib logging**. It is
`console.*` plus winston/pino/bunyan, and assertions are **spy-based**
(`vi.spyOn(console, "warn")`), not `caplog`. So "what is an emit" and "what pins
it" both need re-grounding.

**Method.** No engine code. A module with a pure-arg `console.warn` emit and an
impure-arg `console.log` emit; tests that (a) spy-assert the emit, (b) only check
the return, (c) pin a side effect hidden in an impure emit arg. Direct mutation
for the verdict; tree-sitter for emit classification.

**Verdict (TL;DR).** **Observable ports — the mechanic is the functional `→null`
splice, the detection surface re-grounds onto `console.*` + spies.** Nullifying a
pure-arg `console.warn(...)` kills a spy-asserting test and **survives** a
return-only test (data-flow-preserving — the cleanest signal, no equivalent-mutant
ambiguity, exactly as in Python). The same three conservatism gates Python uses
(`_is_emit`: unused-return, emit-method, logger-shaped receiver, pure args) port
directly; the impure-arg case is a real **false-PROVEN trap** that the pure-args
gate closes. `console` is the universal-receiver analog of stdlib `logging`.

---

## Emit detection — Python's three gates, re-grounded on `console.*`

The tree-sitter classifier, mirroring `_is_emit`:

```
console.warn("low stock")              -> EMIT (mutable): console.warn
console.log("audited", record(level))  -> NO-SIGNAL (impure args — nullify drops a side effect)
logger.info(x)                         -> EMIT (mutable): logger.info
audit.log(entry)                       -> NO-SIGNAL (receiver 'audit' not logger-shaped)
console.table(data)                    -> NO-SIGNAL (method 'table' not an emit)
const r = console.warn("x")            -> NO-SIGNAL (not a bare statement — return used)
```

The three gates map one-to-one:

| Python `_is_emit` gate | JS analog |
|------------------------|-----------|
| `ast.Expr` (unused return) | bare `expression_statement` (not assigned/returned) |
| `<logger>.<method>`, method ∈ `_EMIT_METHODS` | `console.<m>`, `m ∈ {log, info, warn, error, debug, trace}` |
| receiver ∈ `_LOGGER_NAMES` (`log`/`logger`/`logging`) | receiver ∈ `{console, logger, log, logging}` — `console` is the stdlib-logging analog |
| pure args (no nested `Call`/`Await`) | no nested `call_expression`/`await_expression` in args |

`console` plays the role stdlib `logging` plays in Python — the universally
detectable surface. Library loggers (winston `logger.info`, pino `log.info`)
extend the receiver set via the same heuristic, and a config-supplied
metric/event backend (`statsd.incr`, a custom `emit()`) extends it further —
exactly Python's note that the rubric scopes to the universal surface and
extends by config.

**One refinement the adapter must add (lower-bound miss in this spike's
classifier):** a member-expression receiver like `this._logger.error(...)` or
`self.log.info(...)` is *missed* here because the classifier matched the full
receiver text. Python handles it by extracting the trailing attribute
(`getattr(receiver, "attr", "")` → `_logger` → `logger`). The JS adapter must
likewise take the **trailing identifier** of a member-expression receiver. Until
it does, the miss is in the safe direction (a real logger read as no-signal → a
missed gap, never a false PROVEN) — the same posture as Python's
"unconventionally-named loggers are missed."

## The signal — data-flow-preserving nullify

Nullify the pure-arg emit `console.warn("low stock")` → `void 0`:

```
emit pinned    (vi.spyOn(console,"warn"); toHaveBeenCalledWith("low stock"))  -> KILL
emit unobserved (only the return value is asserted)                            -> survive
```

The spy-asserting test dies; the return-only test survives because the emit's
return is unused — nullifying it changes no data flow. This is the cleanest of
all five levels' signals: there is no equivalent-mutant ambiguity, because
deleting an emit is never behaviorally equivalent to a test that checks it (the
same property Python's `make_observable_mutants` docstring claims).

The `caplog` analog is `vi.spyOn(console, <method>).mockImplementation(() => {})`
+ `expect(spy).toHaveBeenCalled[With](...)`; restore with `vi.restoreAllMocks()`
in `afterEach`.

## The impure-arg trap → `no-signal` (false-PROVEN averted)

`console.log("audited", record(level))` hides a side effect in an emit arg —
`record()` pushes to a module array. Nullifying the **whole emit statement** also
drops `record(level)`, so a test pinning that side effect dies:

```
audit return + side effect  (expect(audited).toEqual([7]))  -> KILL   (but it pins record(), NOT the emit)
```

That KILL is a **false PROVEN** — a side-effect assertion miscredited as an
observability assertion. The pure-args gate (no nested call in the emit args)
classifies this emit as `no-signal` and never generates the mutant — the same
lower-bound discipline Python applies, and the same shape as the resilient
spike's multi-arg `no-signal` guard.

## Scope

- **Cleared:** observable operationalizes in JS via the proven `→null` splice on a
  `console.*`/logger emit; the three detection gates + pure-args guard port; the
  impure-arg false-PROVEN trap is closed; the spy-based assertion is the `caplog`
  analog. **With the coverage, mutation, node-mapping, and resilient spikes, the
  four mutation-based levels are shown to port to JS** — functional / behavioral /
  resilient / observable.
- **Performant** is the one level that is **not mutation-based** — it is
  *detection*-based (does a covering test assert a time/resource bound), so it was
  never in this spike series' perturb-and-see-if-a-test-dies mechanism. It is
  spiked separately in `P7-performant-spike.md`: the inline-timing-assert path
  (`performance.now()` in a normal test) ports directly and reuses this map's
  covering-test set; vitest `bench()` is scoped out (separate execution mode, no
  per-test coverage).
- **Adapter to-do (noted, not blocking):** trailing-identifier extraction for
  member-expression receivers (`this._logger`); the receiver/method sets are a
  config surface (winston/pino/metric backends), as in Python.
- **Not spiked:** async emits inside `await`-bearing bodies (the pure-args gate
  already excludes `await` args, the safe direction); template-literal emit args
  with embedded calls (excluded by the same gate).

## Reproduce

```bash
cd /tmp/sm-vitest-spike/obs       # src/store.js (pure + impure emits), test/store.test.js (spy/return/side-effect)
# pure-arg console.warn -> void 0 : spy-pinned KILL, return-only survive
# impure-arg console.log(...,record()) -> void 0 : side-effect test false-kills (why no-signal)
npx vitest run test/store.test.js --no-coverage --reporter=verbose
```
