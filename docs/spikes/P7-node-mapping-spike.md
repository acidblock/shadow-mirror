# P7 — Node mapping (Istanbul coverage ⋈ tree-sitter mutation, by line)

**Question.** The engine's three coordinate systems — coverage, mutation sites,
operation tree — are joined in Python by **one key: the physical line number**.
`coverage.py` reports per line, `ast` nodes carry `lineno`, the operation tree is
built from `ast`; `map.py`'s `_site_verdict` gates a mutation site's `lineno`
against `executed_lines` and selects covering tests via `line_tests[lineno]`. JS
breaks the single-substrate assumption: **two parsers** — Istanbul (Babel coords:
1-based line, statement/branch maps) for coverage, tree-sitter (byte coords) for
mutation. So node mapping must prove: (1) the two parsers' line numbers **agree**,
(2) Istanbul's `s`-index attribution **expands to the same `line → {test_ids}`
map** `run_coverage_with_contexts` produces, and (3) a site's covering tests can
be **selected and run alone** (the `run_selected_tests` analog) to the correct
verdict — the integration the mutation spike stopped short of.

**Method.** No engine code. A 4-function JS module; per-test attribution via the
`__VITEST_COVERAGE__` snapshot-diff (the coverage spike's mechanism), keyed by
`(file, test-name)`; Istanbul's `statementMap` from `coverage-final.json`;
tree-sitter for the mutation sites. A ~140-line harness builds the line map,
joins each site, and closes the selection loop through vitest. The sample is
built to contain the two traps a clean-looking sample hides.

**Verdict (TL;DR).** **Line-level join is clean and is parity.** The parsers
agree on line numbers once the one cross-parser seam — tree-sitter's 0-based row
+1 = Istanbul's 1-based line — is reconciled. Istanbul's `s`-index attribution
expands to the `line → {test_ids}` map, and the selection loop runs *only* a
site's covering tests to the correct verdict in **both** directions — kills on
pinned sites and a survive (`GAP_UNASSERTED`) through selection on a weak-tested
one, including the over-selection case (two tests on a line) either way. Two
silent-correctness traps surfaced and are now guarded: **statement→line
expansion** must use the full `start..end` span (start-line-only mis-reads a
covered continuation-line site as a false `GAP_UNEXERCISED`), and **test-ID
selection** must be anchored (bare-name `-t` silently over-matches).

---

## The join — line agreement, one off-by-one

Each tree-sitter operator site's line, reconciled with `start_point[0] + 1`,
lands on the Istanbul statement that owns it — every site, no drift:

```
site (tree-sitter)        Istanbul statement     agree?
L2  '+'  in add           s0  L2                 yes
L5  '<'  in clamp         s1  L5–L7 (the `if`)   yes
L11 '*'  in applyMarkup   s4  L11                yes
L14 '+'  in total.reduce  s6  L14                yes
L15 '*'  in total         s5  L14–L15            yes
```

The **0-based-row vs 1-based-line** off-by-one is the only cross-parser
convention gap that bites at line granularity (columns would add a second —
Istanbul's UTF-16 columns vs tree-sitter's byte columns — which is why column
granularity is scoped out below). Reconciled once, the join is exact.

## Trap 1 — expand statements to their FULL line span

Istanbul's `s`-index → lines must use the whole `start..end` span, not the start
line. `coverage.py`'s `executed_lines` is physical-line based; start-line-only
under-resolves multi-line statements, so a covered site on a *continuation* line
reads as never-executed — a false gap. `total`'s return spans `s5: L14–L15` with
the `*` on L15:

```
L15 in executed (full-span)?  True   ->  PROVEN              (correct)
L15 in executed (start-only)? False  ->  GAP_UNEXERCISED     (FALSE — site runs, is pinned)
```

`executed_lines` (full-span) = `{2,5,6,7,8,11,14,15,18}` — note L15 and L7 (the
`if`'s closing brace line) are present only because the span expansion reaches
them. **SPI requirement:** the coverage adapter expands every executed statement
(and branch) to its full line span before building `executed_lines` /
`line_tests`.

## Trap 2 — test IDs must be selection-addressable (anchored)

Attribution keys on the human test name; selection consumes `vitest -t <regex>`,
which substring/regex-matches the *full* test name. Bare names collide:

```
bare     -t 'markup'    -> matches 'markup' AND 'markup exact pin'   (2)
anchored -t '^markup$'  -> matches 'markup'                          (1)
```

The selection loop groups covering ids by file and builds an **anchored,
regex-escaped alternation** `^(<name1>|<name2>)$` per file. **SPI consequence:**
the coverage capability's return type is `line → {test_id}` where `test_id` must
be selection-addressable (file + exact name), not a bare display string.

## The selection loop — the actual payoff

Each site resolves its covering tests from the line map and runs *only* those
against the spliced mutant — to the correct verdict in **both** directions:

```
L2  '+'->'-'  : PROVEN          (selected 1: add is pinned exactly)
L5  '<'->'>=' : PROVEN          (selected 1: clamp pins both arms)
L11 '*'->'/'  : PROVEN          (selected 2: markup, markup exact pin)
L15 '*'->'/'  : PROVEN          (selected 1: total pins the continuation-line multiply)
L18 '*'->'/'  : GAP_UNASSERTED  (selected 2: scale weak A, scale weak B)
```

This closes the chain the mutation spike left open: attribution → line map →
*test selection* → mutant run → verdict — with a survive (`GAP_UNASSERTED`)
through selection, not only kills.

**Over-selection safety, demonstrated (not just argued).** Two lines carry two
tests each, so line-level **over-selects** on both — and the verdict is correct
either way: L11's exact-pin test kills the arithmetic (the weak `>0` test can't
hide the kill → PROVEN), while L18's two tests are *both* weak (`> 0`), neither
pins the `*`, so it correctly **survives** even with both selected. Over-selection
cannot manufacture a false PROVEN (extra tests don't execute the mutated
statement, so they pass and can't kill) and cannot hide a real gap (L18). That is
the line-granularity property that makes column precision unnecessary.

## Scope — line-level is parity; column is beyond it

- **Line-level join is exactly what the engine does** — Python is line-keyed
  end-to-end, with the identical dense-line behavior. Column granularity is
  *beyond* parity, not required, and would force clearing the UTF-16-vs-byte
  column-convention gap. Scoped out deliberately.
- **Over-selection on dense lines (`a; b;`, or two tests on one line) is a
  performance cost, never a correctness one.** Line-level never *under*-selects:
  any test covering a statement covers its line, so `line_tests[L]` is a superset
  of the precise covering set. Extra tests don't execute the mutated statement →
  they pass → they can neither manufacture nor hide a kill. The verdict is
  identical to precise selection, just with more tests run. (One imprecision that
  *is* visible: on a dense line, an executed sibling statement can tip a
  `GAP_UNEXERCISED` to `GAP_UNASSERTED` — same as Python's line-keyed behavior.)
- **Operation-tree ↔ mutation join is trivially clean** — both are tree-sitter,
  one parser, byte ranges. The only two-parser seam is coverage ⋈ mutation, the
  one proven here.
- **Resilient is not "same splice, different target" — it needs its own spike.**
  `mutate.py`'s resilient signal swaps a raised type to a sentinel
  (`GeneratorExit`) that no `except` clause matches. **JS has no typed `catch`** —
  `catch (e)` binds everything; type discrimination is a runtime `instanceof`
  *inside* the body. So the `_SENTINEL` trick has no direct analog and the
  resilient signal is structurally different in JS, not just a different node to
  splice. Branch-arm mapping adds a second wrinkle (Istanbul gives an
  implicit-`else` arm an *empty* position — arm identity comes from the per-test
  `b`-arm attribution, not a source position). Before any SPI freezes the
  resilient capability shape, this gets a dedicated spike.
- **TS** through the transpile/source-map layer — unspiked.
- **Robustness note (selection regex):** an anchored `-t` that matches *zero*
  tests in a file exits `0` — which would read as a false **survive**
  (`GAP_UNASSERTED`), not a false kill. Covering names come from real
  attribution so they always exist, but a mis-escaped/mis-anchored name would
  silently pass. The adapter should assert the matched-test count equals the
  selected-id count.

With the coverage and mutation spikes, this clears the **behavioral + functional
signal chain end-to-end in JS**: parse → attribute per test → expand to line map
→ locate site → select covering tests → mutate → verdict.

## Reproduce

```bash
cd /tmp/sm-vitest-spike/mut          # 5-fn calc.js, 7 tests, _attrib.setup.js, node_map_spike.py
/tmp/sm-vitest-spike/.ts-venv/bin/python node_map_spike.py
# join+selection: each site -> right covering tests selected -> correct verdict,
#   incl. L11 PROVEN (over-selected 2) and L18 GAP_UNASSERTED (over-selected 2, survive)
# trap 1: full-span PROVEN vs start-only false GAP_UNEXERCISED on L15
# trap 2: bare -t 'markup' matches 2, anchored '^markup$' matches 1
```
