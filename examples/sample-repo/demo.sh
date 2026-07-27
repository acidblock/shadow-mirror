#!/usr/bin/env bash
# Shadow Mirror — Rung 1 demo. Runs the engine and mutmut on the same tiny sample
# and contrasts them. "Extensive runtime logging": everything is teed to a log file
# the container leaves behind (SM_DEMO_LOG, default /work/demo.log).
set -uo pipefail
LOG="${SM_DEMO_LOG:-/work/demo.log}"
exec > >(tee "$LOG") 2>&1

rule() { printf '\n========== %s ==========\n\n' "$1"; }

echo "Shadow Mirror demo — semantic coverage vs. a flat mutation score"
echo "sample: inventory.py (restock · apply_markup · withdraw)"

rule "1. sm map -vv  — the five-level map, with the mutation process logged live"
sm map inventory.py --tests test_inventory.py -vv

rule "2. sm plan  — what to test next, with honest stubs"
sm plan inventory.py --tests test_inventory.py

rule "3. mutmut  — the familiar mutation-testing reference"
mutmut run || true
mutmut results || true

rule "the contrast (the honest one)"
cat <<'NOTE'
mutmut and sm overlap on operators but measure different things:

  mutmut  → one flat score + a pile of surviving mutants to triage.
  sm      → per function, per LEVEL: which kind of correctness is unproven
            (functional / behavioral / resilient / observable) — and `sm plan`
            hands you the exact stub to close it.

Same underlying survivors; sm turns the pile into a plan. Neither is a strict
superset of the other (test-selection means they can even disagree) — sm's value
is structure, attribution, and what-to-test-next, not raw detection power.
NOTE
echo
echo "(full log saved to $LOG)"
