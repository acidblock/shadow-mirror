# P7 — .tsx / JSX support (where it ports, and the one runtime seam that gates it)

**Question.** The TS adapter cleared the source-map seam: Istanbul reports coverage
at original ``.ts`` lines despite the type-stripping transform. ``.tsx`` adds JSX —
a much larger transform: ``<span>{n * 2}</span>`` desugars into a
``jsx(...)`` / ``createElement(...)`` call, *relocating* embedded logic into call
arguments. Two questions follow, and the spike's job is to decide which (if either)
blocks: **(1)** does the JSX desugar still round-trip coverage — in particular,
does a *JSX-embedded expression* attribute to its original ``.tsx`` line? **(2)**
``.tsx`` component tests need a runtime the others don't (a DOM ``environment`` and
the project's ``setupFiles``) — does the adapter's machinery still supply it?

**Method.** No engine code. (a) Parse a representative ``.tsx`` with
``tree-sitter-typescript``'s ``language_tsx`` and check the site-finder node
types/fields. (b) **Risk 1, React-free:** a ``.tsx`` with a JSX-embedded binary
expression, a ``throw`` in a component, and a ``console.*`` emit, transpiled with a
no-op ``jsxFactory`` (so no React/jsdom needed) — run vitest+istanbul, read which
lines the ``statementMap`` carries. (c) **Risk 2:** a target ``vitest.config.ts``
with a marker ``setupFiles``, run with and without the adapter's injected
``--config``, and see whether the target config survives.

**Verdict (TL;DR).** **``.tsx`` *logic* ports under the identical line-join the
TS/JS path uses — the gate is a test-runtime seam in ``coverage()``, not the
grammar.** The ``language_tsx`` grammar is site-finder-compatible (JSX adds only
ignored node types); the coverage source-map round-trip holds *through* the JSX
desugar, including a JSX-embedded expression (it attributes to its original
``.tsx`` line). The one blocker is structural and narrow: ``coverage()`` injects a
``--config`` to add the per-test attribution setup, and vitest's ``--config``
**replaces** the target config rather than merging — dropping the
``environment: 'jsdom'`` and ``setupFiles`` that *component-render* tests need. So
pure-logic ``.tsx`` (tests that call functions and assert returns/throws) works
today with only the grammar binding; render-style ``.tsx`` needs ``coverage()`` to
**inherit** the target's resolved config. That is a ``coverage()`` change
(``mergeConfig``), named here, not built.

---

## Grammar — ``language_tsx`` is site-finder-compatible

Parsing a ``.tsx`` with components, a typed throw, ``.map`` over JSX children, a
try/catch, and an arrow component: ``has_error=False``, and every node type +
field the site-finders use is present and identically named to JS/TS.

| Site-finder need | ``.tsx`` result |
|------------------|-----------------|
| ``function_declaration`` / ``arrow_function`` + ``name``/``body`` fields | resolve, even with ``: JSX.Element`` return types and destructured typed props |
| ``return_statement`` / ``throw_statement`` / ``catch_clause`` | present |
| ``binary_expression`` (+ ``operator``), ``new_expression`` (+ ``constructor``/``arguments``), ``call_expression``, ``member_expression``, ``expression_statement`` | present |
| ``string`` / ``number`` / ``true`` / ``false`` / ``null`` | present (shared literals) |
| JSX adds | ``jsx_element``, ``jsx_expression``, ``jsx_opening_element``, ``jsx_closing_element``, ``jsx_attribute`` — **none matched by the site-finders → ignored** |

Two operator interactions, both benign:

- **functional sees ``return <jsx>``** as a mutable site (the return child is a
  ``jsx_element`` / ``parenthesized_expression``, not ``null``/``undefined``), so
  ``return <jsx> → return null`` is emitted. Meaningful: a component that renders
  ``null`` is caught by any render/return test. (An *expression-bodied* arrow
  component — ``const A = () => <b/>`` — has no ``return_statement``, so it is *not*
  a functional site → no-signal there. Minor, lower-bound, not incorrect.)
- **behavioral sees JSX-embedded expressions** — ``{n * 2}`` is a
  ``binary_expression`` inside a ``jsx_expression``; the operator finds and swaps
  it. This is real embedded logic, not a spurious site.

## Risk 1 — the JSX desugar still round-trips coverage (cleared)

``.tsx`` transpiled with a no-op ``jsxFactory: h`` (React-free), three tests
covering an embedded expr (L5), a component ``throw`` (L10), an emit (L16):

```
coverage keyed on: _tsxspike.tsx
statement lines + hits: L2:1, L2:2, L5:1, L9:1, L10:1, L12:0, L16:1, L17:1
  L5  JSX-embedded binary expr (n * 2)  -> REPORTED hit=1
  L10 throw new RangeError              -> REPORTED hit=1
  L16 console.info emit                 -> REPORTED hit=1
  L12 return after the throw            -> hit=0 (correctly unexercised)
```

Despite ``<span>{n*2}</span>`` desugaring into an ``h("span", …, n*2)`` call, the
embedded ``n*2`` is attributed to its original line **5**. The source-map
round-trip the TS spike cleared survives the larger JSX transform. The same
``executed_lines`` + ``line_tests`` machinery (built from this ``statementMap``)
therefore lands JSX-embedded sites correctly.

**Note (not a trap):** istanbul folds the embedded ``n*2`` into the enclosing
return's single L5 counter rather than emitting an independent statement for it. The
behavioral mutation site (``n*2``) is *also* on L5, so the gate
(``lineno in executed_lines``) passes and ``line_tests[L5]`` carries the covering
test — the established line-level over-selection-is-safe property covers it. No
column-level precision needed.

## Risk 2 — the gate: ``coverage()``'s injected ``--config`` replaces the target's

A target ``vitest.config.ts`` whose ``setupFiles`` drops a sentinel, run two ways:

```
run WITHOUT --config   -> marker RAN     (target vitest.config.ts is read)
run WITH   --config X   -> marker ABSENT  (injected --config REPLACED it)
```

vitest's ``--config <file>`` is authoritative, not merged. ``coverage()`` *must*
inject a ``--config`` (it adds the ``__VITEST_COVERAGE__`` per-test attribution
``setupFiles`` and the istanbul ``coverage`` block), so it drops whatever the target
config set — including ``environment: 'jsdom'`` and the project's own
``setupFiles`` (e.g. ``@testing-library/jest-dom`` matchers). A ``.tsx`` test that
renders a component (imports ``@testing-library/react``, touches ``document``) then
errors at collection — ``document is not defined`` — erroring the whole run, the
same failure shape as the scoped-out ``bench()`` case.

The breakage is **narrow and precise**:

- ``run_all`` / ``run_selected`` pass **no** ``--config`` (only ``--no-coverage``),
  so they already inherit the target's ``environment`` / ``setupFiles``. The
  green-gate and mutation-kill checks work for ``.tsx`` unchanged.
- Only ``coverage()`` — the per-test attribution build — replaces the config. It is
  the *single* place ``.tsx`` render-style projects break.
- Pure-logic ``.tsx`` (tests that call exported functions and assert returns/throws,
  no DOM) needs no ``environment``/``setupFiles`` and works today (Risk 1's
  experiment is exactly this shape).

## Scope — what ports now, and the named build slices

- **Ports under the existing engine, grammar binding only:** ``.tsx`` *logic*
  (functional / behavioral / resilient / observable / performant on component and
  helper logic) when the project's tests are pure-logic, and the coverage seam for
  JSX-embedded sites. The grammar binding is the same shim shape as ``TsAdapter``:
  ``_TreeSitterAdapter("tsx", tsts.language_tsx())``.
- **Build slice 1 (the gate): ``coverage()`` must inherit the target config. —
  DONE.** ``coverage()`` now detects a target ``vitest.config.*`` / ``vite.config.*``
  and generates an injected config that ``import``s it and ``mergeConfig``s the
  attribution ``setupFiles`` + istanbul block onto the target's *resolved* config
  (object or sync/async function export). The no-target path is byte-identical to
  the pre-merge config (the JS/TS conformance suite guards it); the merge path is
  guarded by ``test_ts_coverage_inherits_target_vitest_config`` (an isolated
  ``conformance_js/inherit/`` fixture whose ``vitest.config.ts`` sets
  ``environment: happy-dom`` + a marker ``setupFiles`` — a single verdict proves
  environment + setupFiles + attribution all survived the merge). Fail-loud: an
  import/merge error surfaces as a vitest failure, never a silent standalone
  fallback. This also future-proofs ``.ts`` / ``.js`` projects that rely on
  ``setupFiles``. See ``_treesitter._config_js`` / ``_find_target_config``.
- **Build slice 2: the ``.tsx`` grammar binding + a render fixture. — DONE.**
  ``TsxAdapter`` (``shadow_mirror/adapters/tsx.py``) binds ``language_tsx`` over the
  shared ``_TreeSitterAdapter`` — kept SEPARATE from ``TsAdapter`` because the tsx
  grammar reads ``<T>`` as JSX, so ``.ts``'s ``<T>expr`` cast needs
  ``language_typescript`` (verified: the cast errors under ``language_tsx``). The
  fixture (``conformance_js/tsx/``) is real Preact components rendered to the
  inherited happy-dom (``test_tsx_component_render_verdicts``): functional
  (``return <jsx>``→null caught by the render), behavioral (a render test pins
  ``{n*2}``), observable (a ``console.*`` spy-asserted). Rigor is the proven/gap
  SPLIT — ``Badge.behavioral=proven`` vs ``Loose.behavioral=gap`` proves attribution
  reached the JSX-embedded site, not a uniform degrade. Resilient/performant omitted
  (byte-identical to the same constructs in any function, already TS-conformance-proven).
- **Out of scope (stated):** expression-bodied arrow components are not functional
  sites (no-signal, lower-bound); ``.d.ts`` ambient files (no runtime); the
  ``jsx`` *runtime* selection (classic vs automatic) folds into slice 1 — inheriting
  the target config inherits its jsx settings too, so it is not a separate seam.

## Reproduce

```bash
cd tests/fixtures/conformance_js     # vitest 4.x + @vitest/coverage-istanbul + esbuild
# grammar: parse a .tsx with tree_sitter_typescript.language_tsx, confirm
#   function/throw/catch/binary/return nodes present, jsx_* nodes ignored.
# Risk 1 (React-free): _tsxspike.tsx (embedded {n*2}, a throw, a console emit) with a
#   no-op jsxFactory config; npx vitest run --coverage; statementMap reports L5/L10/L16.
# Risk 2: a target vitest.config.ts with a marker setupFile; run with vs without
#   --config; the marker runs only WITHOUT --config -> injected --config replaces it.
```
