# P7 — Per-test coverage attribution in JS (vitest + Istanbul)

**Question.** Shadow Mirror's whole method rests on **per-test coverage
attribution**: for each line, *which tests execute it?* In Python this is
`coverage.py`'s `dynamic_context="test_function"`, consumed by
`run_coverage_with_contexts` as a `line → {test_ids}` map. That map is what lets
the engine *select the covering tests* during a mutation, instead of re-running
the whole suite per mutant. Before committing to a JS adapter (tree-sitter parser
+ Istanbul coverage + vitest runner), the make-or-break question is: **can vitest
emit per-test coverage attribution at all?** If it can only produce one merged,
suite-wide report, the adapter is a different (and much weaker) design.

**Method.** No engine code, no committed npm project — a throwaway 2-file project
in `/tmp`. One source module, two functions (`add`, `mul`); two tests, each
hitting exactly one function. Run under `coverage.provider: "istanbul"` and ask,
three ways, whether coverage can be attributed *per test* rather than merged.
Read the raw output; don't theorize from the API.

**Verdict (TL;DR).** **Yes — three ways, with a clear preferred path and a robust
fallback.** The default merged run gives only suite-wide coverage (useless for the
method). But (a) **N isolated runs** via the public `-t <name>` / per-file filter
yield clean per-test maps, and (b) a **single instrumented run** can attribute
per-test by snapshot-diffing `globalThis.__VITEST_COVERAGE__` — the live,
cumulative Istanbul counter — in `beforeEach`/`afterEach`. (b) is the exact JS
analog of `dynamic_context`, in one run. The risk surface and the
single-run-vs-N-run tradeoff are now known *before* the SPI is frozen. Proven at
**statement and branch** granularity — branches being the case the levels
actually consume. Scope: this clears the *coverage-attribution* risk only; JS
source-mutation and node-mapping are separate, unspiked capabilities.

---

## Target

- **Module:** `src/calc.js` — `export function add(a,b){return a+b}` and
  `export function mul(a,b){return a*b}`. Two statements, one per function.
- **Tests:** one `add` test and one `mul` test (as separate files, then as two
  tests in one file). Deliberately disjoint so a correct per-test map must show
  each test touching exactly one statement.
- **Config:** `coverage.provider: "istanbul"`, `reporter: ["json"]`,
  `include: ["src/**"]`. vitest 4.1.8, `@vitest/coverage-istanbul` 4.1.8, Node 22.

## The three approaches

### 1. Merged run — the default, and not enough

```
$ npx vitest run --coverage
# coverage/coverage-final.json  →  calc.js  s: {0:1, 1:1}  f: {0:1, 1:1}
```

Both statements covered, **one merged report**. No way to tell which test hit
which line. This is `coverage.py` *without* `dynamic_context` — line%, nothing
more. An adapter built on this could compute line coverage but could **not** do
test-selection during mutation, so it could not operationalize the behavioral /
resilient / observable levels. Insufficient on its own.

### 2. N isolated runs — public API, N× cost, robust

Filter to one test (by file or by `-t <name>`), one run each:

```
$ npx vitest run test/add.test.js --coverage   # calc.js s: {0:1, 1:0}  → add touches s0 only
$ npx vitest run test/mul.test.js --coverage   # calc.js s: {0:0, 1:1}  → mul touches s1 only

# same result by name, within a single file (the others are skipped):
$ npx vitest run test/both.test.js -t "add case" --coverage   # s: {0:1, 1:0}
$ npx vitest run test/both.test.js -t "mul case" --coverage   # s: {0:0, 1:1}
```

Clean, disjoint, **test-function granularity** (not just per-file). Built only on
documented CLI flags, so it survives vitest internals churn. Cost is N runs for N
tests — acceptable for the small covering-test sets that mutation test-selection
actually uses, expensive as a way to build the *initial* full attribution map.

### 3. Single-run snapshot-diff — the `dynamic_context` analog

Inside the worker, `globalThis.__VITEST_COVERAGE__` **is** the live Istanbul
counter, and it is **cumulative** across tests in that worker:

```
after "add case":  calc.js s: {0:1, 1:0}
after "mul case":  calc.js s: {0:1, 1:1}   # s0 stayed 1, s1 went 0→1
```

So per-test attribution is a before/after **diff** in `beforeEach`/`afterEach`:

```
add case -> ["calc.js#s0"]
mul case -> ["calc.js#s1"]
```

Exactly the `line → {test_ids}` map `run_coverage_with_contexts` produces — in a
**single instrumented run**. Caveat: `__VITEST_COVERAGE__` is a vitest-internal
global (not `__coverage__`, which is *absent* in the worker scope under the
vitest provider — checked). It works on 4.1.8 but is not a documented contract;
a rename would break it. That is precisely why approach 2 exists as the fallback.

**Branches, not just statements (the level-bearing case).** The functions above
are branchless (`branchMap: {}`), but the levels live on *branches* — resilient
is error-arms, behavioral on a ternary needs to know *which* arm ran. Istanbul's
branch counter `b` has a **different shape** from `s`: `{id: [armCount,
armCount]}` (one count per arm), so the diff is per-arm, not per-id. Adding
`clamp(x){ if (x<0) return 0; return x; }` and one test per arm, the single-run
diff attributes correctly:

```
clamp negative -> ["calc.js#s2", "calc.js#s3", "calc.js#b0.0"]   # taken arm
clamp positive -> ["calc.js#s2", "calc.js#s4", "calc.js#b0.1"]   # fallthrough arm
```

Each test lands on the specific arm it exercised — the signal the resilient and
behavioral levels consume.

**Shared lines attribute to every covering test.** `s` is a hit *count*, not a
flag, so a second test hitting an already-covered line still trips `v > before`
(1→2). Two tests both calling `add` each attribute to `s0` — neither is missed.

**Sequential-only.** Approach 3 is correct only because within-file tests run
sequentially against that one shared cumulative counter (vitest's default).
Per-*file* parallelism is safe — separate workers, separate counters. But
`test.concurrent` races: a concurrent sibling's increments leak into this test's
afterEach diff. Demonstrated — two `test.concurrent` tests, one calling `add`
(s0), one calling `mul` (s1):

```
conc add -> ["calc.js#s0"]              # correct
conc mul -> ["calc.js#s0", "calc.js#s1"]   # WRONG — picked up add's s0
```

The adapter using approach 3 must assert non-concurrent within-file execution
(or detect `test.concurrent` and fall back). Approach 2's `-t` filter is the
concurrency-safe path.

## What this means for the adapter SPI

- **The coverage-attribution risk is cleared** — at statement *and* branch
  granularity, the level-bearing case. This is the single biggest P7 unknown, and
  it's answered. It is **not** the whole P7 gate: JS *source mutation* and the
  *statement→operation-tree-node* mapping are separate capabilities, neither
  spiked here. tree-sitter's byte-range nodes make both plausible and lower-risk,
  but they remain unproven — the precise claim is "coverage attribution works,"
  not "the JS adapter works."
- **JS proven, TS unverified.** The spike used plain `.js`. Per-test attribution
  *through* the TypeScript transform + source-map layer (does `b`/`s` indexing
  still line up with original-source positions after transpile?) is an open
  question the SPI should not assume away.
- **The SPI's coverage capability should be specified as `per_test_coverage(...)
  → line→{test_ids}`, not "merged coverage".** Both the Python and JS adapters
  meet it; a merged-only ecosystem would fail the capability and that failure
  should be explicit, not silently degraded to line%.
- **Preferred JS impl: single-run snapshot-diff (3), fallback: N isolated `-t`
  runs (2).** Ship the adapter so it can fall back when the internal global is
  unavailable — and so external vetting sees a public-API path that does not
  depend on a private symbol.

## Reproduce

```bash
mkdir -p /tmp/sm-vitest-spike/{src,test} && cd /tmp/sm-vitest-spike
cat > package.json <<'EOF'
{"name":"spike","type":"module","private":true}
EOF
cat > vitest.config.js <<'EOF'
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { coverage: {
  provider: "istanbul", reporter: ["json"], include: ["src/**"], reportsDirectory: "coverage" } } });
EOF
cat > src/calc.js <<'EOF'
export function add(a, b) { return a + b; }
export function mul(a, b) { return a * b; }
EOF
cat > test/both.test.js <<'EOF'
import { expect, test, beforeEach, afterEach } from "vitest";
import { writeFileSync, appendFileSync } from "node:fs";
import { add, mul } from "../src/calc.js";
const LOG = "/tmp/sm-vitest-spike/snap.log";
function counts() {
  const c = globalThis.__VITEST_COVERAGE__ || {}, out = {};
  for (const [f, d] of Object.entries(c)) out[String(f).split("/").pop()] = { ...(d && d.s) };
  return out;
}
let before;
beforeEach(() => { before = counts(); });
afterEach((ctx) => {
  const after = counts(), touched = [];
  for (const [f, s] of Object.entries(after))
    for (const [k, v] of Object.entries(s))
      if (v > (before[f]?.[k] ?? 0)) touched.push(`${f}#s${k}`);
  appendFileSync(LOG, `${ctx.task.name} -> ${JSON.stringify(touched)}\n`);
});
writeFileSync(LOG, "");
test("add case", () => { expect(add(2, 3)).toBe(5); });
test("mul case", () => { expect(mul(2, 3)).toBe(6); });
EOF
npm install -D vitest @vitest/coverage-istanbul >/dev/null 2>&1

# (1) merged — one report, no per-test split:
npx vitest run --coverage >/dev/null 2>&1
python3 -c "import json; d=json.load(open('coverage/coverage-final.json')); print(list(d.values())[0]['s'])"   # {'0':1,'1':1}

# (3) single-run per-test diff:
npx vitest run test/both.test.js --coverage >/dev/null 2>&1
cat snap.log    # add case -> ["calc.js#s0"]   /   mul case -> ["calc.js#s1"]
```
