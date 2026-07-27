# Canonical SM-* phase definitions

> **Naming choice.** The shadow-mirror loop has **seven** phases, numbered
> **SM-0 through SM-6**. Each number is bound to exactly one verb. The count
> is seven; the lowest index is zero; `SM-6: Iterate` is a real phase, not a
> loop-back arrow.

**This document is the canonical definition of the phase model.** It stands
on its own: no external project, package, or framework is required to read,
understand, or apply it. Every reference implementation (Python, Swift, or
any third party) **conforms to this document** — on any discrepancy between
an implementation and this file, this file is canonical and the
implementation is the bug.

Each phase below references the `phase` field of every `ReceiptV1`
(see [receipt-format-v1.md](receipt-format-v1.md)).

---

## SM-0: Hypothesize

State a falsifiable claim about an observed symptom.

- **Input.** A symptom, anomaly, or design question — anything that
  produces uncertainty about whether the system behaves as expected.
- **Output.** A hypothesis with three parts:
  1. The symptom, stated precisely.
  2. The boundary (what passes, what fails).
  3. The falsifiable claim ("the failure occurs because X, observable
     via Y").

**Applied to a unit test.** A test that fails intermittently under
concurrency: hypothesis = "the shared counter is not protected by a lock;
this can be proven by observing two concurrent writers losing one update."

**Receipt mapping.** Records into `ReceiptV1.hypothesis`. The
`phase` field of the receipt is `"SM-0"`.

---

## SM-1: Instrument

Choose observation points that can answer the SM-0 question.

- **Input.** The SM-0 hypothesis.
- **Output.** A list of probes — function entry/exit traces, log fields,
  metrics, span attributes, eBPF kprobes, Playwright network captures,
  pytest fixtures. Each probe is justified by which assertion it will
  feed.

**Applied to a unit test.** Wrap the shared counter's `increment()` call
with a `caplog`-friendly logger that records the (thread_id, before, after)
triple on every call.

**Receipt mapping.** Records into `ReceiptV1.instrumentation` (a frozen
tuple of probe identifiers). Phase = `"SM-1"`.

---

## SM-2: Assert

Generate the test predicates that, accumulated, prove or disprove SM-0.

- **Input.** The SM-1 probe set.
- **Output.** One or more predicates. Each predicate is testable in
  isolation. Predicates are tagged with the operation-tree node they
  cover, so coverage can be measured in SM-5.

**Applied to a unit test.** Two assertions: (1) for every observed
(thread_id, before, after) record, `after == before + 1`; (2) the final
counter value equals the number of increments.

**Receipt mapping.** Records into `ReceiptV1.assertion`. Phase = `"SM-2"`.

---

## SM-3: Execute

Run the instrumented test. Collect traces, metrics, outcomes.

- **Input.** The SM-2 assertions, the SM-1 probes, and the system under
  test.
- **Output.** Raw evidence (logs, traces, metrics) + a verdict on each
  predicate. The verdict is the basis for `ReceiptV1.outcome`.

**Applied to a unit test.** `pytest tests/test_counter.py -k concurrent`
with the probe-aware fixture active. The captured records make the lost
update visible.

**Receipt mapping.** Records into `ReceiptV1.outcome` ∈
{`verified`, `falsified`, `inconclusive`} and `ReceiptV1.evidence_ref`
(content-addressable hash of the raw evidence blob). Phase = `"SM-3"`.

---

## SM-4: Document

Produce a durable artifact that ties everything together.

- **Input.** The SM-3 evidence and verdict.
- **Output.** A `ReceiptV1` written to a content-addressable store. The
  receipt is enough, by itself, for a third party to reconstruct what was
  hypothesized, how it was tested, and what the verdict was.

**Applied to a unit test.** The receipt emitted here carries the SM-3
result — e.g. `ReceiptV1(phase="SM-3", outcome="falsified",
hypothesis="...", instrumentation=("counter_logger",), assertion="...",
ts="...", evidence_ref="sha256:...")` — saved alongside the test run.
(The `phase` field names the step the receipt *records*, SM-3; the act of
emitting and storing it is SM-4.)

**Receipt mapping.** This phase **emits** the `ReceiptV1`; it does not
write into a single field. Phase = `"SM-4"` on the meta-receipt that
records the documentation step itself, if one is produced.

---

## SM-5: Review

Meta-validate the work: coverage, assertion quality, proof soundness.

- **Input.** All receipts from SM-0..SM-4 for this hypothesis.
- **Output.** A judgment on whether SM-0 was actually answered, or
  whether the loop needs another pass. Coverage signal: did the
  instrumentation reach every operation-tree node the hypothesis
  required? Assertion signal: were the predicates strong enough to
  distinguish true from false?

**Applied to a unit test.** Inspect the receipts: was the probe inside
the lock-critical region? Did the assertion catch the lost-update case
the hypothesis predicted, or only a different symptom?

**Receipt mapping.** Optionally produces its own `ReceiptV1` with
`phase="SM-5"`, `hypothesis` reformulated as a meta-claim about the
proof's soundness.

---

## SM-6: Iterate

Decide whether to refine the hypothesis, deepen instrumentation, or
declare done.

- **Input.** The SM-5 judgment.
- **Output.** Either (a) a refined hypothesis and a new loop iteration
  starting at SM-0, or (b) a "done" verdict that closes the loop.

**Applied to a unit test.** SM-5 said the assertion missed a race
between increment and read. SM-6 produces a refined hypothesis: "the
race spans not just increment-vs-increment but increment-vs-read." A
new loop begins.

**Receipt mapping.** Optionally produces its own `ReceiptV1` with
`phase="SM-6"`. The receipt's `outcome` reflects the iteration decision
(`verified` = loop closes, `falsified` = original hypothesis was wrong
in a way that needs a new start, `inconclusive` = another pass needed).

---

## Phase count contract

The loop has exactly seven phases, in canonical order:

| Index | Phase  | Verb        |
|-------|--------|-------------|
| 0     | `SM-0` | Hypothesize |
| 1     | `SM-1` | Instrument  |
| 2     | `SM-2` | Assert      |
| 3     | `SM-3` | Execute     |
| 4     | `SM-4` | Document    |
| 5     | `SM-5` | Review      |
| 6     | `SM-6` | Iterate     |

Any conforming implementation MUST expose these seven phases, in this
order, with these exact string values. A conformance test asserts the
invariant. For example, the reference Python package (`ROADMAP.md` → P0)
satisfies it as:

```python
from shadow_mirror import PHASES
assert len(PHASES) == 7
assert [p.value for p in PHASES] == [
    "SM-0", "SM-1", "SM-2", "SM-3", "SM-4", "SM-5", "SM-6",
]
```

An implementation in any other language asserts the equivalent. On any
discrepancy between an implementation and this document, **this document
is canonical** and the implementation is the bug.
