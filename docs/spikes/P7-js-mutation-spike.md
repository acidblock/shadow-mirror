# P7 — JS source mutation (tree-sitter byte-splice + vitest)

**Question.** The behavioral / functional / resilient levels are *mutation*
signals: perturb the source, run the covering tests, and a level is `proven`
only if a test dies. In Python the engine does this with `ast.parse` → mutate the
AST node → `ast.unparse` — a full regenerate-from-AST roundtrip. **tree-sitter
has no `unparse`** (it is a parser, not a code generator), so the JS adapter
cannot mirror that mechanic. The make-or-break questions are therefore *not*
"can you mutate JS" (trivially yes) but:

1. Does tree-sitter node-addressing port the engine's **operator set** cleanly?
2. Does **byte-range splicing** — the natural pairing for a parser with no
   codegen — avoid a *false-kill* trap that `ast.unparse` made impossible?

**Method.** No engine code. tree-sitter's Python binding (same C grammar as any
host binding, so a faithful proxy wherever mutation eventually lives) parses a
3-function JS module; a ~120-line harness locates sites, splices bytes, re-parses
each mutant, and shells out to vitest. Operators swapped to match `mutate.py`'s
reference set. The sample is built so some mutants **die** (pinned) and some
**survive** (the gap signal — the actual product).

**Verdict (TL;DR).** **Yes, and cleaner than Python in one place.** All three
operator classes — arithmetic, comparison, logical — are a *single* tree-sitter
node type (`binary_expression`) with one addressable `operator` field, where
Python needs three (`BinOp` / `Compare` / `BoolOp`). Byte-splice ports the two
commonest mutation mechanics (operator-swap, subexpr→literal) end-to-end: kills
on pinned code, survivals on a weakly-tested function — including the
functional-proven-but-behavioral-gap split the whole engine rests on. The
byte-splice **false-kill trap is real and guardable**: an unparseable mutant
errors the whole vitest suite → `exit=1`, *indistinguishable from a real kill by
exit code alone* — averted by re-parsing each mutant and rejecting `ERROR` nodes
before it ever runs.

---

## Operator-token addressing — uniform, and simpler than Python

`child_by_field_name("operator")` returns the operator token's byte range for
every binary form, multi-char operators included:

```
a+b    -> binary_expression, operator '+'   bytes[22,23]
a<b    -> binary_expression, operator '<'   bytes[22,23]
a&&b   -> binary_expression, operator '&&'  bytes[22,24]
a===b  -> binary_expression, operator '===' bytes[22,25]
a||b   -> binary_expression, operator '||'  bytes[22,24]
```

`mutate.py` dispatches on three AST classes (`_BINOP`/`_CMP`/`_BOOLOP` keyed by
`ast.BinOp` / `ast.Compare` / `ast.BoolOp`). In tree-sitter the whole behavioral
operator class is **one node type, one field** — the swap table is the only
per-language data; the addressing code is uniform. That divergence is a
*simplification*, the opposite of a porting hazard.

## Two mechanically-distinct splices, end-to-end

Byte-splice on the source `src[:start] + replacement + src[end:]`. Bytes
throughout (tree-sitter offsets are **byte** offsets), so multibyte source is
safe by construction. One mutant per parse — length-shifting swaps (`<`→`>=`)
need no offset bookkeeping because the next mutant re-parses from clean source.

**Behavioral — operator-token swap** (against `mutate.py`'s reference set):

```
L2  '+'->'-'  in add(a,b)          exit=1 -> KILLED   (add(2,3)===5 pins it)
L5  '<'->'>=' in clamp(x)          exit=1 -> KILLED   (both arms pinned)
L11 '*'->'/'  in applyMarkup       exit=0 -> SURVIVED (arithmetic unpinned)
L11 '+'->'-'  in applyMarkup       exit=0 -> SURVIVED (gap)
L11 '/'->'*'  in applyMarkup       exit=0 -> SURVIVED (gap)
```

**Functional — subexpr-replace `return <expr>` → `return null`:**

```
L2  return 'a + b' -> null                       exit=1 -> KILLED
L6  return '0' -> null                            exit=1 -> KILLED
L8  return 'x' -> null                            exit=1 -> KILLED
L11 return 'Math.round(...)/100' -> null          exit=1 -> KILLED
```

`applyMarkup`'s test asserts only `> 0`. So its **return is checked**
(`return null` dies — `null > 0` is false) but its **arithmetic is unpinned**
(operator swaps survive). That is the functional-proven / behavioral-gap
distinction — the wedge the engine exists to expose — reproduced natively in JS,
on the JS analog of the Python sample's `apply_markup`.

## The false-kill trap — real, and guarded

`ast.unparse` gives Python a free validity guarantee: a well-formed AST always
unparses to runnable source, so a nonzero test exit always means the test
*detected* the mutation. Byte-splice has no such guarantee. A structure-breaking
splice produces source that fails to load — and vitest reports a load error as a
**nonzero suite exit, identical to a real kill**. A false kill is a false
`proven`: the exact failure the engine exists to prevent.

Demonstrated with a deliberately malformed splice (`+` → `*/`, giving `a */ b`):

```
well_formed(mutant) = False                       # re-parse finds an ERROR node
guarded:   REJECTED pre-run — false-kill averted
unguarded: vitest exit=1  = looks identical to a KILL by exit code alone
```

**The guard is a hard SPI requirement, not a nicety:** every mutant must be
re-parsed and rejected for `root_node.has_error` *before* it is run. The
operator-swap and subexpr→`null` mechanics are valid-by-construction (each
produces a well-formed tree on the sample), but the guard is what makes the
adapter safe for any future *structure-changing* operator (block-replace,
multi-token) — and what lets a nonzero exit be trusted as a kill.

## Scope — what this clears, and what it does not

- **Cleared:** operator-token addressing (uniform across arithmetic / comparison
  / logical), and the two commonest mutation mechanics (token-swap, subexpr→
  literal) end-to-end through vitest, with the false-kill guard. Combined with
  the coverage spike (`P7-vitest-coverage-spike.md`), the behavioral and
  functional level signals are proven to port.
- **Same splice mechanism, different target, unspiked:** `mutate.py`'s other
  three mechanical kinds — identifier/raise-type swap (resilient, JS `throw`),
  const-perturb, and block-replace (`blank-except` analog). All are the same
  byte-splice with a different node target; none is proven here.
- **Resilient level** specifically needs the `throw`-type and `catch`-arm
  analogs of `make_mutants`; the `_SENTINEL` raise-swap trick is Python-specific
  (`GeneratorExit`) and needs a JS equivalent. Unspiked.
- **Node-mapping** (Istanbul `s`/`b` indices ↔ tree-sitter nodes ↔ operation-tree
  nodes) is the remaining unspiked P7 capability. The byte ranges here make it
  plausible (both are byte-addressed) but it is not proven.
- **TS** unverified — same caveat as the coverage spike; the splice is on
  pre-transpile source, but node↔coverage alignment through the source-map is
  untested.

For the eventual demo's "familiar contrast" (the JS analog of mutmut),
**Stryker** is the established JS mutation-testing tool — P7-demo territory, not
this spike.

## Reproduce

```bash
cd /tmp/sm-vitest-spike            # the coverage-spike project (vitest installed)
python3 -m venv .ts-venv && .ts-venv/bin/pip install tree-sitter tree-sitter-javascript
# mut/src/calc.js (add/clamp/applyMarkup), mut/test/calc.test.js (strong add+clamp,
# weak >0 on applyMarkup), mut/mutate_spike.py — the parse->splice->vitest harness.
.ts-venv/bin/python mut/mutate_spike.py
# behavioral: add/clamp KILLED, applyMarkup SURVIVED (gap)
# functional: all returns KILLED
# false-kill: malformed splice REJECTED pre-run; unguarded it would read as a kill
```
