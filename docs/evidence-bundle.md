# Evidence Bundle — the standalone, self-verifying form

A `ReceiptV1` (see `receipt-format-v1.md`) is a compact **attestation**: eight
fields, with an `evidence_ref` that is a sha256 *content-address* of the canonical
map — not the map itself. To read the verdicts later you recompute the map and check
the hash. That is the right default when a map store is available.

An **`EvidenceBundle`** is the standalone form for when the bundle may be the only
artifact that survives a run: the receipt **plus** the canonical map it attests to,
in one JSON object.

```json
{
  "receipt": {
    "schema_version": "1.0",
    "phase": "SM-5",
    "hypothesis": "semantic coverage of <module>",
    "instrumentation": ["python", "coverage.py@7.13.5", "sm-mutation@0.2.0", "sm-rubric@v2"],
    "assertion": "4 nodes, 3 level-gaps (['behavioral','functional','observable','performant','resilient'])",
    "outcome": "inconclusive",
    "ts": "2026-06-04T00:00:00Z",
    "evidence_ref": "sha256:39a088…"
  },
  "evidence": {
    "rubric_version": 2,
    "module": "<module>",
    "line_coverage": { "covered_lines": 14, "num_statements": 15 },
    "nodes": [ { "node_id": "…", "complexity": 1, "executed": true,
                 "levels": { "functional": "proven", "behavioral": "proven",
                             "performant": "n/a", "resilient": "n/a",
                             "observable": "gap-unasserted" } }, … ]
  }
}
```

## The integrity link

The bundle is **self-verifying**. `evidence` is the producer's `canonical_dict`, and
the receipt's `evidence_ref` is the sha256 over that exact canonical JSON, so:

```
bundle.verified  ⇔  sha256(canonical(bundle.evidence)) == bundle.receipt.evidence_ref
```

This makes the bundle **tamper-evident for inconsistency**: edit a verdict in the
embedded map, or change the receipt's `evidence_ref`, and `verified` goes `False`.

It is **not tamper-proof**. An actor who edits the map *and* recomputes a matching
`evidence_ref` produces a consistent-but-forged bundle. Detecting that requires a
**signature over the receipt** — a receipt-chain concern out of scope for v1.
`verified` attests *internal consistency*, not authenticity.

## Why `evidence_ref` does not change

The bundle is a wrapper; `ReceiptV1` stays the frozen v1 format. Provenance
(`instrumentation`) and the embedded map are receipt-/bundle-level data — the
`evidence_ref` hashes only `evidence` (the verdicts), so the same evidence reproduces
the same `evidence_ref` across tool upgrades. Embedding the map alongside the receipt
does not alter the hash; it just removes the need to recompute the map to read it.

## API / CLI

```python
from shadow_mirror.map import build_full_map
bundle = build_full_map(module, tests, cwd).to_bundle(ts)
bundle.verified          # True
bundle.to_json()         # the standalone artifact
EvidenceBundle.from_json(text).verified   # re-verify after a round trip
```

```bash
sm map <module> --tests <tests> --bundle out.json
#   bundle → out.json  (sha256:…, verified=True)
```

The compact `--receipt` form remains available and unchanged; `--bundle` is the
self-contained superset.
