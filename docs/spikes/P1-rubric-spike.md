# P1 — Rubric spike (paper)

**Question.** Can the four coverage levels — functional / behavioral /
performant / resilient — be operationalized into concrete signals, or do they
collapse into subjective vibes? If they can't, the whole engine is not worth
building (the P1 kill-gate).

**Method.** No engine code. Take one real module with a real, thorough pytest
suite; get the `coverage.py` baseline; build the operation tree and the
four-level map *by hand*; then ask whether the map sees anything `coverage.py`
reports as covered. Where a gap is claimed, **confirm it empirically** with a
mutation probe (flip a documented behavior; if every test stays green, the
behavior was unproven).

**Verdict (TL;DR).** **GATE PASSED.** On a module `coverage.py` scores **96 %**,
the by-hand map surfaces **three confirmed behavioral gaps** that `coverage.py`
reports as fully covered, plus two reasoned resilient gaps — and reveals the
Performant level is *not applicable* here, a distinction `coverage.py` has no
concept of. The levels operationalize cleanly; one refinement (an `N/A` verdict)
was discovered.

---

## Target

- **Module:** `shadow_mirror/receipt.py` — the `ReceiptV1` data model (~50 lines
  of logic: `__post_init__`, `to_dict`, `to_json`, `from_dict`, `from_json`).
- **Tests:** `tests/test_receipt.py` — 14 test items, deliberately thorough
  (round-trip, shape, normalization, leniency, error rejection, spec example).

Dogfooding: Shadow Mirror's own evidence record is the system under test.

## `coverage.py` baseline

```
$ pytest tests/test_receipt.py --cov=shadow_mirror.receipt --cov-branch --cov-report=term-missing
Name                       Stmts   Miss Branch BrPart  Cover   Missing
shadow_mirror/receipt.py      42      1      6      1    96%   79
```

`coverage.py` catches exactly **one** thing: line 79 (`raise TypeError(...)` for
a non-string probe in `instrumentation`) never executes, and the branch into it
is partial. Everything else is reported **covered**. A reasonable reading:
"96 %, basically done."

## Operation tree (by hand)

```
ReceiptV1
├── N1  __post_init__  (normalize + validate)
│   ├── N1a  normalize phase     Phase(self.phase)
│   ├── N1b  normalize outcome   Outcome(self.outcome)
│   ├── N1c  normalize instr.    tuple(self.instrumentation)
│   ├── N1d  str-type guard      for field: if not isinstance(str) -> TypeError
│   └── N1e  probe-type guard    if not all(isinstance(str)) -> TypeError   [line 78-79]
├── N2  to_dict      (enum->str, tuple->list, fixed key set)
├── N3  to_json      (sorted keys, ensure_ascii=False)
├── N4  from_dict    (.get(k, default) defaults, str() coercion, drop unknown keys)
└── N5  from_json    (json.loads then from_dict)
```

## The four-level map

Verdicts: **✓ proven** (an assertion pins it) · **▲ gap** (lines execute, nothing
asserts the behavior) · **· N/A** (no behavior of this kind at this node).

| Node | Functional | Behavioral | Performant | Resilient |
|------|:----------:|:----------:|:----------:|:---------:|
| N1a normalize phase   | ✓ | ✓ | · | ✓ (invalid → `ValueError`) |
| N1b normalize outcome | ✓ | ✓ | · | ✓ (invalid → `ValueError`) |
| N1c normalize instr.  | ✓ | ✓ | · | ✓ |
| N1d str-type guard    | ✓ | – | · | ✓ (non-str → `TypeError`) |
| N1e probe-type guard  | – | – | · | ▲ **also caught by coverage.py (line 79)** |
| N2 to_dict            | ✓ | ✓ | · | – |
| N3 to_json            | ✓ (sorted keys) | ▲ **`ensure_ascii=False` unproven** | · | – |
| N4 from_dict          | ✓ | ▲ **`.get` defaults + `str()` coercion unproven** | · | ▲ missing key → `KeyError` unproven |
| N5 from_json          | ✓ | – | · | ▲ malformed JSON unproven |

Two readings of the same module:

- **`coverage.py`:** 96 %. One hole (N1e).
- **Semantic map:** Functional is solid; **Resilient is the *strongest* level**
  (errors well-tested, and `coverage.py` caught the one hole); **Behavioral is
  the weak spot** — and it is exactly the level `coverage.py` cannot see.

## What the map sees that `coverage.py` does not — confirmed

Each gap below is on a line `coverage.py` reports as **100 % covered**. Confirmed
by mutation probe: flip the behavior; if all 14 tests stay green, it was
unproven.

| # | Node·Level | Mutation applied | Result |
|---|-----------|------------------|--------|
| 1 | N3 · behavioral | `ensure_ascii=False` → `True` | **all tests pass** → unicode-preservation unproven |
| 2 | N4 · behavioral | `from_dict` `schema_version` default `SCHEMA_VERSION` → `"9.9"` | **all tests pass** → default-supplying path unproven |
| 3 | N4 · behavioral | `from_dict` `instrumentation` default `()` → `("BOGUS",)` | **all tests pass** → default-supplying path unproven |

The pattern is the point: gaps #2 and #3 live inside `dict.get(key, default)` —
**not an `if`**, so neither line nor branch coverage tracks the default arm.
Gap #1 is a library-flag behavior. A maintainer could make any of these three
changes and ship a silent behavior regression with `coverage.py` green and every
test passing. The map flags precisely those cells.

Two further resilient gaps are reasoned (untested, same confirmation available):
`from_dict` on a missing required key (`KeyError`) and `from_json` on malformed
JSON. Both lines are "covered" on the happy path; neither failure mode is pinned.

## Rubric v0

Operational signal per level. The map's unit is a **(node × level) cell** with a
verdict in `{proven, gap, N/A}`. The headline signal is a cell that is
**line-covered yet `gap`** — "covered but unproven."

| Level | Signal (consume, don't rebuild) | Verdict rule |
|-------|----------------------------------|--------------|
| **Functional** | ≥1 assertion on the node's return/output for representative inputs | `proven` if such an assertion exists; else `gap` |
| **Behavioral** | mutation survival on the node (`mutmut`/`cosmic-ray`) — is the input→output mapping pinned? | `proven` if mutants die; `gap` if a mutant survives a line-covered node |
| **Performant** | ≥1 time / memory / IO bound on the node (`pytest-benchmark` or explicit assert) | `proven` if a bound exists; **`N/A`** if the node has no resource-relevant behavior; else `gap` |
| **Resilient** | each error/`except` branch both executed **and** asserted-upon (right error for the right bad input) | `proven` per branch; `gap` if a failure branch is unexercised or unasserted |
| *(cross-level strength)* | property-based presence (`hypothesis`) | raises confidence on functional + behavioral; not its own level |

## Refinements discovered

1. **A third verdict, `N/A`, is required.** Performant is N/A for every node in a
   pure in-memory module. Without `N/A`, the map would cry "0 % performant" and
   train users to ignore it. The level applies *per node*, not globally.
2. **Behavioral ≈ mutation score is the right operationalization** — validated
   here by hand: three surviving mutants ⇒ three behavioral gaps. This confirms
   the rubric's `mutmut` choice empirically, not by assertion.
3. **The wedge concentrates where `coverage.py` is structurally blind:**
   `dict.get(k, default)` default arms and library-flag behaviors — expressions,
   not `if` statements. This is why the gap survives at 96 %+ coverage.
4. **The map's value tracks where `coverage.py` is weakest.** On this module
   `coverage.py` did well on Resilient (it caught N1e) but is blind to
   Behavioral — and Behavioral is exactly where the real gaps were.

## Kill-gate verdict

**PASS — proceed to P2.** The four levels operationalized into concrete,
consumable signals; the by-hand map beat `coverage.py` on a module `coverage.py`
called 96 % done, and did so with empirical (mutation-confirmed) evidence rather
than opinion. The one refinement (`N/A` verdict, applied per node) is folded
into rubric v0 above and should carry into the P3 rubric v1.

## Reproduce

```bash
# baseline
pytest tests/test_receipt.py --cov=shadow_mirror.receipt --cov-branch --cov-report=term-missing

# confirm a gap (example: gap #1). Tests stay green => unproven.
sed -i '' 's/ensure_ascii=False/ensure_ascii=True/' shadow_mirror/receipt.py
pytest tests/test_receipt.py -q          # 14 passed
git checkout -- shadow_mirror/receipt.py # revert
```
