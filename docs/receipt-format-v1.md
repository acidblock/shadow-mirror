# Receipt Format v1

A **receipt** is the durable, content-addressable record a Shadow Mirror loop
emits at SM-4 (Document). It is enough, by itself, for a third party to
reconstruct what was hypothesized, how it was observed, and what the verdict
was — without access to the system that produced it.

**This document is the canonical definition of the v1 wire format.** It stands
on its own: no external project, package, or framework is required to read,
produce, or verify a receipt. Every implementation conforms to this document —
on any discrepancy between an implementation and this file, this file is
canonical and the implementation is the bug.

The format version is **`1.0`**. Any payload whose `schema_version` is `"1.0"`
is guaranteed to round-trip through JSON without loss.

## Canonical example

```json
{
  "schema_version": "1.0",
  "phase": "SM-0",
  "hypothesis": "the shared counter is not lock-protected; two concurrent writers lose one update",
  "instrumentation": ["counter_logger"],
  "assertion": "for every (thread, before, after) record, after == before + 1",
  "outcome": "verified",
  "ts": "2026-05-31T15:30:00Z",
  "evidence_ref": "sha256:abc123..."
}
```

The canonical serialization is JSON with **sorted keys**, arrays (not tuples),
and string values exactly as shown.

## Field reference

| Field             | Type        | Required | Notes |
|-------------------|-------------|----------|-------|
| `schema_version`  | `string`    | yes      | `"1.0"` for this version. |
| `phase`           | `string`    | yes      | One of the seven phase identifiers: `"SM-0"` .. `"SM-6"`. |
| `hypothesis`      | `string`    | yes      | The falsifiable claim under test. Free-form prose; ideally a single sentence. |
| `instrumentation` | `string[]`  | yes      | Identifiers of the probes active during the observation. May be empty. |
| `assertion`       | `string`    | yes      | The test predicate, in code or prose. |
| `outcome`         | `string`    | yes      | One of `"verified"`, `"falsified"`, `"inconclusive"`. |
| `ts`              | `string`    | yes      | ISO-8601 timestamp; UTC with a `Z` suffix is recommended. |
| `evidence_ref`    | `string`    | yes      | Content-addressable hash of the raw evidence blob. |

## Field-level semantics

### `schema_version`
Strict-equality match. A reader MAY accept other values, but a **verifier**
MUST reject anything other than `"1.0"` unless the consumer has explicitly
opted in to a newer version. This keeps durable receipts unambiguous about
which rules they were written under.

### `phase`
Must be one of the seven canonical phase identifiers defined in
[phases.md](phases.md). The value is the canonical name — `"SM-3"`, never
`"SM_3"` and never the verb `"Execute"`. A receipt records the phase whose
*result* it captures (e.g. an execution result is `phase="SM-3"`, even though
the act of writing and storing it is SM-4).

### `instrumentation`
A JSON array of probe identifiers. The empty array is legal: a receipt may
record an SM-0 hypothesis before any instrumentation has been laid down. An
implementation MAY use an ordered, hashable internal representation (e.g. a
tuple) so long as the serialized form is an array.

### `outcome`
Exactly three values:

- `"verified"` — the evidence supports the hypothesis.
- `"falsified"` — the evidence refutes the hypothesis.
- `"inconclusive"` — the evidence is insufficient or contradictory; another
  loop iteration (SM-6) is required.

A path that merely *executed* is not `"verified"`. Verification requires an
assertion that could have failed and did not. Absent that, the honest outcome
is `"inconclusive"`.

### `evidence_ref`
A content-addressable reference to the raw evidence (logs, traces, metrics).
The hash algorithm is consumer-defined; `sha256:<hex>` is recommended so a
downstream tool can split on `":"` to select the algorithm. This document does
**not** require the reference to resolve to anything — that is the verifier's
responsibility, not the format's.

## Versioning policy

**May change without bumping `schema_version`:**

- This document's prose.
- The algorithm behind `evidence_ref` (the value is opaque to v1).
- Verifier leniency — accepting receipts with extra, unrecognized fields and
  ignoring them.

**Requires bumping `schema_version`:**

- Adding a required field.
- Removing or renaming a field.
- Changing the type of an existing field.
- Tightening the allowed values of `outcome` or `phase`.

A future bump to `"2.0"` MUST retain a from-`"1.0"` migration path, so receipts
written under v1 stay readable.

## Round-trip guarantee

For any conforming implementation, serializing a receipt and reading it back
yields an equal receipt:

```
read(write(receipt)) == receipt
```

A conformance test asserts this for every field combination, including an empty
`instrumentation` array and each `outcome` value. An implementation that fails
the round-trip is non-conforming.

## Composition — maps and plans (informative)

A single receipt is the **atomic** unit: one phase, one hypothesis, one
verdict. The larger Shadow Mirror artifacts are *collections* of receipts, and
are out of scope for the frozen v1 record itself:

- A **coverage map** is a set of receipts projected onto an operation tree —
  one or more per (node, level) — answering "what is proven, and where are the
  gaps." The map is the receipts plus the tree they are scored against.
- A **test plan** is a set of SM-0..SM-2 receipts (hypothesis → instrumentation
  → assertion) for the gaps a map identified, each carrying the stub that would
  close it.

Because maps and plans are built *from* v1 receipts, freezing the atomic record
is what lets those higher-level artifacts stay verifiable and reproducible. The
schemas for the map and plan envelopes are defined separately and may evolve
without touching this frozen record.
