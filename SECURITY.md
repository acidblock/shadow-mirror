# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** via GitHub's private
vulnerability reporting: [Security → Report a
vulnerability](https://github.com/acidblock/shadow-mirror/security/advisories/new).
Do not open a public issue for anything you believe is security-sensitive.

You can expect an acknowledgment within a few days. Please include a minimal
reproduction if you can — for engine issues, the same module + test file +
command triple the bug-report template asks for.

## Supported versions

| Version | Supported |
|---------|-----------|
| latest release / `main` | ✅ |
| anything older | ❌ — please reproduce on `main` first |

## Threat model — what is in and out of scope

Shadow Mirror **executes the target project's test suite** (via pytest or
vitest) and imports/mutates the target's source. That is its documented job,
not a vulnerability: running `sm map` against a repository is equivalent to
running that repository's own tests, and must only be done on code you would
run anyway. Reports of the form "sm executes code from the analyzed project"
are out of scope by design.

In scope — things we absolutely want to hear about:

- Escaping the target: `sm` writing, deleting, or leaving mutated files
  **outside** the analyzed module (the in-place mutation must be scoped and
  always unwound — see the recovery-sidecar and signal-unwind machinery in
  `shadow_mirror/_run.py`).
- Evidence integrity: forging or laundering a `ReceiptV1`/`EvidenceBundle` so
  that `bundle.verified` passes for a map it does not represent.
- The acceptance gate: a crafted candidate test that `sm verify` accepts
  without a legitimate closure (green-gate bypass).
- The MCP server (`sm-mcp`): path handling that lets a tool call read or write
  outside the caller-supplied `cwd`.
- Classic supply-chain issues in the published package or plugin.
