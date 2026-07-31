## Summary

<!-- What changed and why. Link the issue if one exists (e.g. "Closes #12"). -->

## Test plan

<!-- How this is verified. Bug fix → the regression test that fails without the
     fix. Feature → tests pinning the new contract. "Ran the suite" alone is
     not a test plan. -->

## Breaking changes

None. <!-- Or: what breaks, the migration path, and why it's worth it. -->

## Checklist

- [ ] `python -m pytest tests/ -q` passes locally
- [ ] `ruff check .` passes (no formatter — match the hand-formatted style; see CONTRIBUTING.md)
- [ ] New/changed behavior is covered by tests
- [ ] Docs updated where behavior is documented (README, docs/, docstrings)
