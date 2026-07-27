# Standing constraints — invariant registry

The five standing constraints in [`ROADMAP.md`](../ROADMAP.md) are laws, not
preferences. This file records each as an **invariant** — something that must
always hold — together with how it is enforced and, where enforcement is not
yet possible, the phase at which it becomes testable.

"Recorded as testable invariants where applicable" (ROADMAP P0) means: enforce
what can be enforced today; for the rest, name the exact future test so the
constraint is never quietly forgotten.

| # | Constraint | Invariant (what must always hold) | Enforced by | Status |
|---|------------|-----------------------------------|-------------|--------|
| **C1** | Consume, don't rebuild | Shadow Mirror consumes `coverage.py` / `pytest` as signals; it never forks or reimplements a measurement tool. | The engine shells out to coverage/pytest (`shadow_mirror/_run.py`) — they are *tools*, not import-time deps, so runtime deps stay empty: `tests/test_constraints.py::test_c1_data_model_has_no_runtime_dependencies`. | **Enforced** (P2: engine consumes via subprocess) |
| **C2** | Trust anchor | `sm`'s reported covered-line count equals `coverage.py`'s, exactly, on the same target. | **Enforced now** — `tests/test_engine.py::test_c2_line_parity_exact_integer` (exact integer counts, not the float %). | **Enforced** |
| **C3** | Additive onboarding | `sm` runs on an existing pytest suite with zero test rewrites and zero required annotations. | Fixture test: a vanilla pytest project produces a map with no edits; dogfood at **P8**. | Deferred — **P2 / P8** |
| **C4** | Pristine / standalone | No reference to any other project — internal or external — appears in any shipped, user-facing artifact (`README`, `ROADMAP`, `docs/`, `plugin/`, `shadow_mirror/`, `pyproject.toml`). | **Enforced now** — `tests/test_constraints.py::test_c4_no_foreign_project_references`. | **Enforced** |
| **C5** | Grounded generation is measurable | A generation run grounded on the gap map closes **at least as many** semantic-coverage gaps as an ungrounded baseline, measured by the same map. | The NS-2 grounded-vs-ungrounded benchmark, run as a reproducible eval. Mechanism in place: `closure.check_closure` accepts a candidate only when the *same map* re-scores its target gap→proven (green-gated); `verify.verify_proposals` adds a joint-safety check across the accepted set (`tests/test_closure.py`, `tests/test_verify.py`) — so the comparative eval is measurable by construction. | Deferred — **P8**: the comparative claim (grounded ≥ ungrounded) is unestablished until a real model + external repo. The acceptance *mechanism* shipped in P5; the measurement is dogfooding. |

## Notes

- **Tool vs. project (C4 scope).** The C4 scan denylists *other projects*, not
  the tools the methodology applies to or ships through. `pytest`, `Playwright`,
  `eBPF`/`Cilium`, `OpenTelemetry`, `coverage.py`, `mutmut`, `hypothesis`,
  `PyPI`, and `Claude Code` (the plugin host) are all permitted — they are the
  application surface, not dependencies Shadow Mirror is defined against.
- **Keeping this honest.** When a deferred constraint's phase lands, replace its
  "Deferred" row with the concrete test path, the same way C4 reads today. A
  constraint without either a passing test or a named future test is a gap.
