# P7 — Resilient level in JS (the structurally-different one)

**Question.** The first three P7 spikes (coverage, mutation, node-mapping) cleared
the behavioral + functional chain by *porting* Python mechanics. Resilient is the
one the node-mapping spike flagged as **not a mechanical port**: Python's
resilient signal mutates `except X:` clauses and `raise` statements, keyed on a
syntactic exception type (`ErrorBranch.exc_type`) and a sentinel
(`_SENTINEL = GeneratorExit`, a `BaseException` no normal `raises()` catches).
**JS has no typed `catch`** — `catch (e)` binds everything; type discrimination is
a runtime `instanceof` *inside* the body. So the question is structural: does the
resilient signal operationalize in JS at all, and if so with *what operator set*?

**Method.** No engine code. A throwing module and a recovering module, tests that
pin error behavior at each strength (type / loose / bare / message / recovered
value / type-routing), and direct mutation to read which tests die. tree-sitter
for site classification; vitest for the kill/survive verdict.

**Verdict (TL;DR).** **Resilient ports — but as a different operator set, not a
different splice target.** The `_SENTINEL` analog is a synthesized **non-Error
class** (`throw new RangeError(msg)` → `throw new __SmSentinel(msg)` + appended
`class __SmSentinel { constructor(...a){ this.message = a[0]; } }`): non-Error so
it escapes `toThrow(Error)` exactly as `GeneratorExit` escapes `raises(Exception)`,
`.message=a[0]` so message-pins survive. The `except X:` clause — having no
syntactic home in JS — reappears as a **catch-body `instanceof`**, mutated by a
new resilient operator. Three operators total; the "no typed catch" difference is
real and lands exactly where predicted, in `catch`.

---

## Throw sites — the sentinel, synthesized

vitest's `toThrow` matching, measured against four candidate swaps of
`throw new RangeError("insufficient stock")`:

| swap | `toThrow(RangeError)` | `toThrow(Error)` loose | bare `toThrow()` | `toThrow("msg")` |
|------|:---:|:---:|:---:|:---:|
| builtin `EvalError` | KILL | survive | survive | survive |
| sentinel `extends Error` | KILL | survive | survive | survive |
| **plain object / non-Error** | KILL | **KILL** | survive | survive |

The non-Error row is the true `GeneratorExit` analog. Python's sentinel is a
`BaseException` *specifically* so it escapes `raises(Exception)` — and
`toThrow(Error)` is JS's `raises(Exception)`, killed identically.

**Decision — bare `toThrow()` → `gap-unasserted`, and this is a stricter stance
than Python, stated deliberately (not "parity").** The type-swap's only mutant
for the common `throw new RangeError("msg")` is the type swap (the string arg is
not perturbed, as in Python), and bare `toThrow()` survives it. The *mechanism*
mirrors Python — the broadest catch survives the sentinel (`raises(BaseException)`
survives GeneratorExit too) — but the *frequency* does not: `raises(BaseException)`
is a rare corner in Python, whereas bare `toThrow()` is **mainstream JS**. So
sm-JS flags a standard idiom as a type-gap where sm-Python almost never would.
Two honest resolutions:
1. **Accept the strict stance (chosen here):** bare `toThrow()` genuinely does
   not pin the type, and the resilient level is about pinning the *right error*.
   Calling it `gap-unasserted` is a correct lower bound; the remedy a user takes
   (`toThrow(RangeError)`) is exactly the assertion the level asks for.
2. **Add a throw-presence operator** (remove/neutralize the throw) so bare
   `toThrow()` has a mutant it kills. Rejected for now: it reintroduces the
   deletion-collapses-to-coverage tension Python deliberately avoids (a removed
   throw makes the function return, killing *any* test that reaches it, which
   collapses "asserted" back toward "executed").

This is a model decision the SPI must record, not a free consequence of the
sentinel choice.

**Shipped construct (verified in one run):** swap *only* the constructor
identifier, keep args verbatim, append once:

```js
class __SmSentinel { constructor(...a) { this.message = a[0]; } }   // non-Error
// throw new RangeError("insufficient stock")  ->  throw new __SmSentinel("insufficient stock")
//   withdraw type-pinned  -> KILL     withdraw loose Error -> KILL
//   withdraw bare         -> survive  withdraw message     -> survive
```

Non-Error kills `toThrow(Error)` like the plain object; `.message=a[0]` survives
`toThrow("…")` like the plain object; **args kept verbatim** means no
arg-parsing in the splice. Re-parse the mutant for `has_error` (the mutation
spike's false-kill guard) before running.

### The multi-arg trap → `no-signal` scoping

`.message = a[0]` assumes Error's arg0-is-message convention. `throw new
HttpError(503, "service down")` puts the message in arg1, so the swap sets
`.message = 503` and a `toThrow("service down")` test **false-kills** the type
mutant — a message-pin miscredited as type-pinning, a **false PROVEN** (the exact
thing the engine exists to prevent). Demonstrated: the naive multi-arg swap kills
`http message-pinned`, which survives under the original.

Mitigation — lower-bound, the same discipline as Python emitting no const-perturb
for strings: emit **no type-swap mutant** (→ `no-signal`) unless the throw is a
recognizable `new <ErrorType>(<single string|template>)`. The tree-sitter
classifier:

```
throw new RangeError("insufficient stock")  -> ('RangeError', [string])          MUTABLE
throw new HttpError(503, "service down")     -> ('HttpError', [number, string])    NO-SIGNAL
throw new TypeError(`bad ${x}`)              -> ('TypeError', [template_string])   MUTABLE
throw err                                    -> (no new-expression)                NO-SIGNAL
```

Don't try to preserve arbitrary-constructor messages; scope the operator to
throws it can mutate safely.

## Catch sites — where "no typed catch" actually bites

Python keys resilient on two branch kinds: `raise` (above) and `except`. The
`except` half splits in JS into two structurally-distinct operators.

### Recovery-neutralize — the `blank-except` analog (clean port)

`try { … } catch (e) { return {} }` — perturb the recovered value `{}` → `null`:

```
recovery pinned  (toEqual({}))          -> KILL      (the fallback value is pinned)
recovery weak    (typeof === "object")  -> survive   (typeof null === "object" — unpinned)
```

A test that pins the recovered value dies; one that only checks its shape
survives. Note this operator is **perturb-recovered-value** (`{}`→`null`), not
*blank-the-catch* (body→`undefined`) — and they diverge: blanking to `undefined`
would **kill** the weak `typeof` test (`typeof undefined !== "object"`), whereas
perturb-to-`null` survives it (`typeof null === "object"`). The **perturbation
value is a real SPI parameter** that flips verdicts; the conservative choice is
the value-preserving-shape perturbation (`null`/`+1`/`!bool` as in Python's
`_perturb`), which keeps the signal a lower bound rather than a structural break.

### Type-routing — the new operator, and the resilient/behavioral boundary

`catch (e) { if (e instanceof TypeError) return "type-handled"; throw e; }` — the
`instanceof` *is* JS's spelling of Python's `except TypeError:`. Swap the type
`TypeError` → `RangeError`:

```
routing handled pinned  (toBe("type-handled"))  -> KILL   (TypeError no longer routes -> rethrows)
routing rethrow pinned  (toThrow(RangeError))    -> KILL   (RangeError now routes -> no rethrow)
```

Both arms of the routing die — the handled path and the rethrow path. **Boundary
call:** a catch-body `instanceof` in a routing position is the resilient
operator (it is the error-type discriminator Python mutates as `except X:`); an
`instanceof` *outside* a catch is general type logic and belongs to behavioral if
ever added to the swap table. The level is decided by *context*, not the operator
token.

## The resilient operator set — Python vs JS

| concern | Python (`mutate.py`) | JS (this spike) |
|---------|----------------------|-----------------|
| raised type pinned? | swap type → `GeneratorExit` | swap constructor → synthesized non-Error `__SmSentinel` |
| raised non-string consts pinned? | perturb `Constant` (skip strings) | (same idea; not separately spiked) |
| recovery pinned? | `blank-except` (body → `pass`) | perturb catch-body recovered value |
| **error-type routing pinned?** | **the raise-side sentinel swap (see correction below)** | **swap catch-body `instanceof` type** (new operator) |
| keyed on | syntactic `exc_type` per `except` | throw-expression + catch-body (no syntactic exc_type) |

This is the spike's central finding: resilient is **not** "same splice,
different node." The signal ports, but the operator set is reshaped by JS's
grammar — most sharply, error-type routing has **no direct Python analog** to
splice; the `instanceof`-routing operator is JS-only.

> **Correction (2026-06-04).** The original draft of this section said Python
> "mutates the `except X:` clause itself." It does not. `mutate.make_mutants`
> gives an `except` branch exactly two operators — non-string const-perturb and
> `blank-except` (body → `pass`); the only type-swap (`_swap_raise_type`) is
> **raise-side** (`raise Err(...)` → `raise GeneratorExit(...)`). So error-type
> routing in Python is pinned *indirectly*, via the raise sentinel (the swapped
> type is no longer caught by its `except`), and the `except` branch's own verdict
> is decided by blank-except. This correction is critical: because Python has
> **no** error-type-routing operator, wiring the JS `instanceof`-routing operator
> in would make JS-resilient stricter than Python on routing precision (JS=gap,
> Python=proven) — breaking the cross-language semantic identity P7 requires.
> That is why `instanceof`-routing is **deferred as a rubric decision**, not built
> as a slice-time port. See `shadow_mirror/adapters/javascript.py::_resilient_sites`.

## Scope

- **Cleared:** the resilient signal operationalizes in JS with a three-operator
  set; the sentinel, the multi-arg `no-signal` guard, recovery-neutralize, and
  instanceof-routing are each verified end-to-end through vitest, with the
  resilient/behavioral boundary for `instanceof` decided.
- **Not separately spiked:** non-string const-perturb on throw args (carries over
  from the behavioral/Python work, same mechanism); `finally` blocks; async
  `rejects.toThrow` (vitest's promise form — likely the same `toThrow` matcher,
  unverified); nested/multi-`instanceof` routing chains.
- With the prior three spikes, **four of the five levels are accounted for** —
  functional, behavioral, and resilient port via mutation; performant remains
  `n/a`-by-node as in Python. **Observable — the fifth (rubric-v2) level — is not
  yet spiked.** Its mutation mechanic is the already-proven functional `→null`
  splice (nullify an emit), but its *detection surface* differs structurally:
  Python keys on stdlib `logging` (`_EMIT_METHODS`/`_LOGGER_NAMES`), and **JS has
  no stdlib logging** — it is `console.*` plus winston/pino/bunyan, asserted via
  spies (`vi.spyOn(console, "error")`), not `caplog`. "What is an emit" and "what
  pins it" both need re-grounding. See `P7-observable-spike.md`.

## Reproduce

```bash
cd /tmp/sm-vitest-spike/res          # src/svc.js (throw), src/catch.js (recovery+routing), test/*
# throw sentinel: type+loose KILL, bare+message survive; multi-arg -> false PROVEN (why no-signal)
# catch: recovery perturb {}→null (pinned KILL / weak survive); instanceof swap (both routing arms KILL)
npx vitest run test/svc.test.js test/catch.test.js --no-coverage --reporter=verbose
```
