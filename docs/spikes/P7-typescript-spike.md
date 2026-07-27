# P7 — TypeScript via the source-map seam (the one risk that could sink it)

**Question.** The JS adapter joins two coordinate systems by physical line number:
Istanbul coverage (Babel/istanbul positions) ⋈ tree-sitter mutation (byte → line).
For `.ts`, a transform sits between source and execution: vitest transpiles TS to
JS (esbuild) and Istanbul instruments around that transform. The grammar swap
(`tree-sitter-javascript` → `tree-sitter-typescript`) is mechanical — TS is a
superset, the function/`throw`/`catch`/`binary_expression` nodes are the same, the
extra type-annotation nodes are just nodes the site-finders ignore. The **one seam
that can sink TS** is the source-map round-trip: does Istanbul report coverage
against the **original `.ts` source lines** (which is what tree-sitter parses), or
against the **transpiled JS positions** (which would put the two parsers in
different coordinate systems and break every join)?

**Method.** No engine code. A `.ts` module whose function is preceded by
**type-only declarations that vanish on transpile** — an `interface` (L2–L5) and a
`type` alias (L6) — so the emitted JS shifts `lineTotal` (L8) several lines up. Run
vitest with the same `provider: "istanbul"` config the adapter uses, dump
`coverage-final.json`, and read which line numbers the `fnMap` / `statementMap`
carry. If they are the **`.ts` source lines**, the round-trip holds; if the
**shifted JS lines**, it does not.

**Verdict (TL;DR).** **TS ports — the source-map seam is clean.** Despite the
stripped interface + type alias shifting the function up in the transpiled output,
Istanbul reports `lineTotal` at its **original `.ts` declaration line (8)** and its
body statements at **9–10**, with the coverage entry **keyed on `_tsspike.ts`** (the
source path). vitest's esbuild transform + `@vitest/coverage-istanbul` remap
coverage to original-source positions; those are exactly the positions
`tree-sitter-typescript` sees parsing the same `.ts`. The coverage⋈mutation join is
therefore line-for-line identical to the JS case — the node-mapping spike's whole
chain (full-span expansion, anchored selection, per-test attribution) carries over
unchanged.

---

## The measurement

`_tsspike.ts` — type-only lines above the function, so transpile drops L2–L6:

```ts
// L1 comment
export interface Order {        // L2  — stripped
  id: number;                   // L3
  qty: number;                  // L4
}                               // L5
export type Sku = string;       // L6  — stripped
                                // (L7 blank)
export function lineTotal(o: Order, price: number): number {   // L8
  const subtotal: number = o.qty * price;                      // L9
  return Math.round(subtotal * 100) / 100;                     // L10
}
```

`npx vitest run _tsspike.test.ts --config <istanbul cfg> --coverage`, then
`coverage-final.json`:

```
coverage keyed on: _tsspike.ts
fnMap:          [{ name: lineTotal, declLine: 8, locLine: 8 }]
statementMap:   [{ s:0, line: 9, hit:1 }, { s:1, line: 10, hit:1 }]
```

L8/L9/L10 are the **`.ts` source lines**. Had coverage reported transpiled-JS
positions, the stripped L2–L6 would have pulled `lineTotal` to ~L2–L3 and the join
against tree-sitter (which parses the original `.ts`) would mis-key every site.
It does not — the positions are source-relative, no off-by-N from the transform.
(Whether Istanbul instruments pre-transform or remaps post-transform via the source
map is immaterial to the adapter: the *reported* positions are `.ts`-source, which
is the only property the join needs. No source-map warnings emitted in the run.)

## Why the rest is mechanical, not risky

With the seam clear, a `TsAdapter` (or a `language`-parameterized `JsAdapter`) is a
grammar swap plus a coverage `include` glob:

| Concern | Disposition |
|---------|-------------|
| Parser | `tree-sitter-typescript` (superset grammar); `_FN_TYPES`, `throw_statement`, `catch_clause`, `binary_expression`, `return_statement` node types are shared with JS. |
| Type-annotation nodes | Extra nodes (`type_annotation`, `interface_declaration`, …) the existing `_walk`-based site-finders simply never match. No new handling. |
| Mutation byte-splice | Operator / return / emit splices do not touch types, so a mutant stays valid TS; the `has_error` well-formedness guard re-parses with the TS grammar. |
| coverage / line_tests / executed_lines | Key on `.ts`-source lines (this spike) → identical full-span-expansion + anchored-selection logic as JS. |
| `_match_entry` | Already keys on path/name; the coverage entry is keyed on the `.ts` path. |

## Scope

- **Cleared:** the source-map round-trip — coverage on transpiled TS reports
  original-`.ts`-source positions, so the two-parser join that the JS adapter
  relies on holds for `.ts` with no new reconciliation. This was the one seam the
  node-mapping spike explicitly left "unspiked."
- **Mechanical follow-on (the build, not a risk):** add `tree-sitter-typescript`
  to the `[js]` extra (or a `[ts]` extra), parameterize the parser + coverage
  `include`, and add a `.ts` conformance fixture mirroring a Python module (the
  same GROUND-TRUTH methodology).
- **Scoped out (stated):** `.tsx`/JSX — a distinct grammar (`tree-sitter-tsx`) and
  a distinct transform concern; ambient/declaration (`.d.ts`) files — no runtime,
  no coverage; `tsconfig`-driven path aliases / decorators with `emitDecorator
  Metadata` — transform-config surface beyond the line-position seam this spike
  cleared. None affects the join; each is its own slice if pursued.

## Reproduce

```bash
cd tests/fixtures/conformance_js     # has vitest 4.x + @vitest/coverage-istanbul + esbuild
# write _tsspike.ts (interface+type above an L8 function), _tsspike.test.ts, an
# istanbul-provider config including _tsspike.ts; then:
npx vitest run _tsspike.test.ts --config _tsspike.config.mjs --coverage
node -e 'const r=require("./_tscov/coverage-final.json"); /* fnMap.decl.start.line == 8 */'
# fnMap declLine 8 + statementMap lines 9,10 == original .ts source -> seam clear
```
