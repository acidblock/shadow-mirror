# Grounded generation, end to end

This walks the **agent-integration loop** that P5 ships: Shadow Mirror produces a
brief, an agent (here, a human acting as one) writes candidate tests, and
`sm verify` accepts only the ones that *legitimately* close a gap — no model is
embedded in the tool, and nothing auto-merges.

The transcript below is a real run against `tests/fixtures/resilient_demo/`.

## 1. Get the brief

```bash
sm plan tests/fixtures/resilient_demo/orders.py \
        --tests tests/fixtures/resilient_demo/test_orders.py --brief
```

The brief lists four gaps, each with its call signature, the **proof obligation**
(which mutation the test must make fail), and the acceptance contract. Two excerpts:

```
3. charge / functional (gap-unexercised) — the return path never runs under the suite
   obligation: assert the exact return value; a return→None mutation must fail the test
   stub:       assert charge(<amount>) == <EXPECTED>
4. refund / resilient (gap-unexercised) — the error branch never runs under the suite
   obligation: pin the error path (pytest.raises, or the recovered value) …
   stub:       with pytest.raises(LookupError): refund(<amount>, <ledger>)
```

## 2. Write candidates (the agent's job)

One file per gap. The suite already does `import orders` (and `import pytest`), so a
candidate references them directly. Four genuine closures — and one deliberately
wrong test, to show the gate rejects it rather than laundering it green:

```python
# apply_discount / behavioral — pins the operator, not a loose bound
def test_apply_discount_value():
    assert orders.apply_discount(100, {"SAVE10": 0.1}, "SAVE10") == 90.0

# apply_discount / resilient — pins the except-branch recovery
def test_apply_discount_unknown_code_recovers():
    assert orders.apply_discount(100, {}, "MISSING") == 100.0

# charge / functional
def test_charge_returns_amount():
    assert orders.charge(5) == 5

# refund / resilient
def test_refund_unknown_charge_raises():
    with pytest.raises(LookupError):
        orders.refund(5, [])

# charge / functional — DELIBERATELY WRONG (red on the real code)
def test_charge_wrong_value():
    assert orders.charge(5) == 6
```

A proposals manifest maps each `(node_id, level)` to its candidate file:

```json
[
  {"node_id": "…orders.py::apply_discount", "level": "behavioral", "candidate": "c_apply_behavioral.py"},
  {"node_id": "…orders.py::apply_discount", "level": "resilient",  "candidate": "c_apply_resilient.py"},
  {"node_id": "…orders.py::charge",         "level": "functional", "candidate": "c_charge_functional.py"},
  {"node_id": "…orders.py::refund",         "level": "resilient",  "candidate": "c_refund_resilient.py"},
  {"node_id": "…orders.py::charge",         "level": "functional", "candidate": "c_charge_red.py", "label": "RED"}
]
```

## 3. Verify

```bash
sm verify tests/fixtures/resilient_demo/orders.py \
          --tests tests/fixtures/resilient_demo/test_orders.py \
          --proposals proposals.json
```

```
sm verify — tests/fixtures/resilient_demo/orders.py
4/5 proposals accepted

    node / level                              verdict    detail
---------------------------------------------------------------
 1  apply_discount/behavioral                 ACCEPT     legitimate closure
 2  apply_discount/resilient                  ACCEPT     legitimate closure
 3  charge/functional                         ACCEPT     legitimate closure
 4  refund/resilient                          ACCEPT     legitimate closure
 5  charge/functional                         reject     suite-not-green: combined suite fails on the unmutated module

joint check (4 accepted together): SAFE — all targets hold
```

Exit code `1` (not every proposal landed). What the run shows:

- **Grounding works.** Four briefed gaps closed by tests aimed straight at the
  obligation — no guessing which line to touch.
- **The gate is honest.** The wrong test (`charge(5) == 6`) is **rejected**, not
  credited. `build_full_map` ignores pytest's exit code, so without the green-gate
  this red test would read as "always killed → proven" and *vacuously* close
  `charge/functional`. The gate is what keeps grounding from laundering broken
  tests.
- **The set is jointly safe.** The four accepted candidates don't just each close
  their target against the baseline — appended *together* they leave every target
  proven and regress nothing. That joint check is what makes "4 accepted" a claim
  you can act on.

`--receipt PATH` persists the report as a content-addressable `ReceiptV1` (SM-5),
tied by `map_ref` to the exact baseline map every proposal was checked against.

> **What stays out of scope here.** This is a *demonstration* that the loop closes
> real gaps, not the controlled **NS-2** claim (grounded generation measurably
> beats an ungrounded baseline). That needs a real model and an external repo and
> is deferred to P8. See [`../../ROADMAP.md`](../../ROADMAP.md) (P5 increment 2).
