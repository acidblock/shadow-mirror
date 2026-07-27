# P7 — Performant level in JS (the detection-based one)

**Question.** Performant is the fifth level's odd sibling: it is the only one that
is **not mutation-based**. The other four perturb the source and watch a test die;
performant is pure **detection** — `map.py`'s `_timing_test_funcs` scans the
*test* AST for a test that asserts a time/resource bound (a `benchmark` fixture
arg, or a `perf_counter` / `monotonic` / `process_time` reference), and the
verdict is simply `PROVEN if a covering test is a timing test else NA` (no
mutation, no `gap`). So nothing about the mutation machinery answers whether
performant ports; the open question is narrow and specific: **does the JS
detection surface re-ground cleanly, and is the JS "benchmark" a test the
attribution machinery can even see?**

**Method.** No engine code. A `hotLoop` module; one normal test with an inline
`performance.now()` budget assertion, one normal correctness-only test, and a
vitest `bench()` block. Run under `vitest run` (the attribution mode) to see what
it collects; tree-sitter to classify which tests assert a bound.

**Verdict (TL;DR).** **Performant ports — via the inline-timing-assert path,
which reuses the already-proven covering-test set; the dedicated-benchmark path
does not, and is scoped out.** A `performance.now()` budget assertion inside a
normal `test()` is a normal covering test the attribution sees, and a tree-sitter
scan detects it exactly as `_timing_test_funcs` detects `perf_counter`. vitest's
`bench()`, by contrast, **errors under `vitest run`** ("only available in
benchmark mode") and yields no per-test coverage — so it can never be a covering
test. The verdict rule (`PROVEN if a covering test is a timing test else NA`)
ports verbatim; only the detection surface re-grounds.

---

## The two forms, and which one the attribution machinery sees

Python's `_timing_test_funcs` recognizes two ways a test asserts a bound — and
*both* are normal pytest tests that run under coverage (so both are covering
tests):

| Python form | covering test? | JS analog | covering test? |
|-------------|:---:|-----------|:---:|
| `perf_counter`/`monotonic`/`process_time` inline | yes | `performance.now()`/`.measure()`/`.mark()` inline | **yes** |
| `benchmark` fixture arg (pytest-benchmark) | yes (normal test) | vitest `bench()` | **no — separate mode** |

The divergence is the most important finding. In Python the dedicated-benchmark
form (pytest-benchmark) is just a normal test with a `benchmark` parameter, so it
runs under coverage and attributes to a node. In JS the dedicated-benchmark form
(`bench()`) is a **separate execution mode**:

```
$ npx vitest run test/work.test.js      # the attribution mode
Error: `bench()` is only available in benchmark mode.
      Tests  no tests                    # a bench() in the file errors the whole run
```

So `bench()` benchmarks are invisible to the per-test coverage machinery — and
even if ingested separately (`vitest bench`), they produce no `line → {test_ids}`
attribution, so they could never tie a bound to a specific operation-tree node.
The dedicated-benchmark form is therefore out of scope for attribution-based
performant detection in JS.

## The inline form ports directly

Both normal tests run under `vitest run`, so the timing test is a covering test
like any other. The tree-sitter scan — the `_timing_test_funcs` analog — keys on
the re-grounded surface (`performance.<now|measure|mark>`):

```
test 'hotLoop stays under budget'   -> TIMING-ASSERT  (performant PROVEN where it covers a node)
test 'hotLoop correctness only'     -> no timing assert -> NA contribution
```

Combined with the node-mapping spike's `line → {test_ids}` map, the verdict is
the exact Python rule with nothing new: for a node, `perf = PROVEN if any
covering test is in the timing set else NA`. No mutation, no new join — performant
is the cheapest level to port precisely *because* it is detection-based and the
covering-test set is already built.

## Scope

- **Cleared:** performant operationalizes in JS via inline `performance.*` budget
  assertions in normal tests; detection is a tree-sitter scan of the test source
  (the `_timing_test_funcs` analog), and the verdict reuses the proven
  covering-test set. **With the coverage, mutation, node-mapping, resilient, and
  observable spikes, all five rubric-v2 levels are now shown to port to JS** —
  functional / behavioral / resilient / observable via mutation, performant via
  detection.
- **Scoped out (a real Python divergence, stated):** vitest `bench()` — a
  separate execution mode that errors under `vitest run` and yields no per-test
  coverage. JS performant is the inline-assert form only; the dedicated-benchmark
  form has no attribution-visible analog. (A future adapter could ingest
  `vitest bench` output separately, but it would attribute at file/suite
  granularity at best, not per node.)
- **Detection surface is a config seam**, as in Python: the timing-name set
  (`performance.now`/`.measure`/`.mark`, and a project's own `Date.now()`-based
  helper) extends by config, the same way the observable receiver set does.

## Reproduce

```bash
cd /tmp/sm-vitest-spike/perf      # src/work.js (hotLoop), test/work.test.js (inline timing + correctness)
npx vitest run test/work.test.js --no-coverage    # both normal tests run; a bench() here would error the run
# tree-sitter scan flags 'hotLoop stays under budget' as the timing test (performance.now)
```
