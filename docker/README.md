# Shadow Mirror — container demo (Rung 1)

A reproducible, runs-anywhere demonstration of the engine on a tiny sample, with
**mutmut** alongside it as the familiar mutation-testing reference. This is the
canonical "show it at work" surface — an OCI image, no Anthropic/Claude coupling.

## Run it

From the **repo root** (the build context is the repo, so the engine installs from
local source — no PyPI, no git auth):

```bash
docker build -f docker/Dockerfile -t shadow-mirror-demo .
docker run --rm shadow-mirror-demo
```

The demo (`examples/sample-repo/demo.sh`) runs, teeing everything to `/work/demo.log`:

1. `sm map -vv` — the five-level map with the mutation process logged live.
2. `sm plan` — the ranked gaps + honest stubs to close them.
3. `mutmut run` / `mutmut results` — the familiar flat mutation score.
4. The contrast.

On the sample, `sm map` reports (verified):

```
function        cx  func beha perf resi obse
apply_markup     1    ✓    ▲    –    –    –     ← checked, but the arithmetic isn't pinned
restock          1    ✓    ✓    –    –    –
withdraw         2    ✓    ✓    –    ·    –     ← the out-of-stock raise is never tested
```

— and `sm plan` hands back `assert apply_markup(<cost>, <rate>) == <EXACT>` and
`with pytest.raises(ValueError): withdraw(<level>, <amount>)`. **mutmut** finds the
same surviving mutants but as a flat pile; `sm` attributes them to a *function and a
level* and tells you what to write. Neither is a strict superset (test-selection
means they can disagree) — `sm`'s value is structure and what-to-test-next, not raw
detection count.

## Dev container

`.devcontainer/devcontainer.json` builds the same image for an editor; open it and
run `bash /work/demo.sh`.

## Rung 2 — browsers (Playwright)

The base image is a swappable `ARG`. Point it at a **trusted Playwright image** and
add UI tests:

```bash
docker build -f docker/Dockerfile \
  --build-arg BASE_IMAGE=mcr.microsoft.com/playwright/python:v1.50.0-noble \
  -t shadow-mirror-demo .
```

(Providing a custom image / Helm chart is a future option.) Note: mapping *UI-level*
"proven" is an open design question — today `sm` maps the server-side Python a UI
test drives, not the flow itself.

## Verification status — verified end-to-end

The image **builds and runs** (`docker build` + `docker run`), and the whole demo
works in the pinned `python:3.12-slim` base — including **mutmut**, which segfaults
on the host's pre-release 3.14 but runs clean here. The run corroborates the honest
contrast: mutmut reports **11 surviving mutants — all in `apply_markup` and
`withdraw`** (3 killed of 14), the exact two functions `sm` flags as gaps. mutmut
gives the flat pile; `sm` attributes it (`apply_markup/behavioral`,
`withdraw/resilient`) and hands the stub. `demo.sh` still guards the mutmut step
(`|| true`) so the demo degrades gracefully if a host runs it on an unstable CPython.
