---
name: shadow-mirror
description: Run the Shadow Mirror validation loop (SM-0..SM-6) on a symptom, a module, or a diff — to prove correctness, plan tests, or map coverage.
arguments:
  - name: symptom
    description: The observable failure or anomaly to investigate
    required: false
  - name: phase
    description: Start at a specific phase (hypothesize, instrument, assert, execute, document, review, iterate)
    required: false
---

# /shadow-mirror

Explicit entry point to the Shadow Mirror loop. The full methodology — phase
definitions, decomposition levels, and tool patterns — lives in the
**`shadow-mirror` skill** (`skills/shadow-mirror/SKILL.md`); this command is the
launcher so you don't duplicate it here.

## What to do when invoked

Work through the seven-phase loop as defined in the skill:

```
SM-0 Hypothesize → SM-1 Instrument → SM-2 Assert → SM-3 Execute
                 → SM-4 Document → SM-5 Review → SM-6 Iterate
```

- If `--symptom` is given, open **SM-0** with that as the observed symptom and
  form a falsifiable claim from it.
- If `--phase` is given, jump straight to that phase and continue forward.
- Otherwise start at **SM-0** and ask for the symptom or target to validate.

Pull the operational detail (the four decomposition levels, assertion patterns,
execution commands, coverage-review heuristics) from the `shadow-mirror` skill
and its `references/`. The canonical phase spec is `docs/phases.md` in the repo.

## Usage

```
/shadow-mirror                              # start a fresh loop at SM-0
/shadow-mirror --symptom "API returns 500"  # start with a known symptom
/shadow-mirror --phase instrument           # jump to a specific phase
```
