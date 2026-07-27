"""``sm`` command-line entry point (the ``map`` subcommand)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import json

from ._diff import changed_lines
from .adapters import adapter_for
from .brief import build_brief
from .delta import build_delta
from .map import build_full_map
from .plan import build_plan
from .verify import Proposal, verify_proposals

__all__ = ["main"]


def _now() -> str:
    # timezone.utc (not the 3.11+ datetime.UTC alias) — the package floor is 3.10.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _configure_logging(verbosity: int) -> None:
    """`-v` → per-node verdict rows (INFO); `-vv` → per-mutant kill/survive (DEBUG).
    Silent by default — a library import attaches no handler."""
    if not verbosity:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger("shadow_mirror")
    root.setLevel(logging.INFO if verbosity == 1 else logging.DEBUG)
    root.addHandler(handler)


def _cmd_map(args: argparse.Namespace) -> int:
    smap = build_full_map(args.module, args.tests, cwd=args.cwd, adapter=adapter_for(args.lang))
    print(smap.canonical_json() if args.json else smap.to_text())
    if args.receipt:
        Path(args.receipt).write_text(smap.to_receipt(_now()).to_json() + "\n", encoding="utf-8")
        print(f"\nreceipt → {args.receipt}  ({smap.evidence_ref()})", file=sys.stderr)
    if args.bundle:
        bundle = smap.to_bundle(_now())
        Path(args.bundle).write_text(bundle.to_json() + "\n", encoding="utf-8")
        print(f"\nbundle → {args.bundle}  ({smap.evidence_ref()}, verified={bundle.verified})",
              file=sys.stderr)
    if args.html:
        from .html import render_html
        Path(args.html).write_text(render_html(smap), encoding="utf-8")
        print(f"\nhtml → {args.html}", file=sys.stderr)
    return 1 if (args.fail_on_gap and smap.gaps()) else 0


def _cmd_plan(args: argparse.Namespace) -> int:
    changed = None
    if args.diff:
        try:
            changed = changed_lines(args.module, args.diff, args.cwd)
        except RuntimeError as exc:
            print(f"sm plan --diff: {exc}", file=sys.stderr)
            return 2
    smap = build_full_map(args.module, args.tests, cwd=args.cwd, adapter=adapter_for(args.lang))
    source = (Path(args.cwd) / args.module).read_text(encoding="utf-8")
    plan = build_plan(smap, source, changed_lines=changed, diff_base=args.diff)
    if args.brief:  # the generation brief: acceptance contract + ranked obligations
        brief = build_brief(plan)
        print(brief.canonical_json() if args.json else brief.to_prompt())
        return 1 if (args.fail_on_gap and plan.items) else 0
    print(plan.canonical_json() if args.json else plan.to_text())
    if args.receipt:
        Path(args.receipt).write_text(plan.to_receipt(_now()).to_json() + "\n", encoding="utf-8")
        print(f"\nreceipt → {args.receipt}  ({plan.evidence_ref()})", file=sys.stderr)
    return 1 if (args.fail_on_gap and plan.items) else 0


def _cmd_verify(args: argparse.Namespace) -> int:
    cmap = build_full_map(args.module, args.tests, cwd=args.cwd, adapter=adapter_for(args.lang))
    manifest = json.loads((Path(args.cwd) / args.proposals).read_text(encoding="utf-8"))
    proposals = [
        Proposal(node_id=e["node_id"], level=e["level"], label=e.get("label", ""),
                 candidate_src=(Path(args.cwd) / e["candidate"]).read_text(encoding="utf-8"))
        for e in manifest
    ]
    report = verify_proposals(cmap, args.module, args.tests, proposals, cwd=args.cwd)
    print(report.canonical_json() if args.json else report.to_text())
    if args.receipt:
        Path(args.receipt).write_text(report.to_receipt(_now()).to_json() + "\n", encoding="utf-8")
        print(f"\nreceipt → {args.receipt}  ({report.evidence_ref()})", file=sys.stderr)
    return 0 if report.all_clear else 1


def _cmd_delta(args: argparse.Namespace) -> int:
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    head = json.loads(Path(args.head).read_text(encoding="utf-8"))
    delta = build_delta(base, head)
    if args.json:
        print(delta.canonical_json())
    elif args.markdown:
        print(delta.to_markdown())
    else:
        print(delta.to_text())
    if args.receipt:
        Path(args.receipt).write_text(delta.to_receipt(_now()).to_json() + "\n", encoding="utf-8")
        print(f"\nreceipt → {args.receipt}  ({delta.evidence_ref()})", file=sys.stderr)
    # Gate (off by default, per C3): regressions always fail; new gaps fail only
    # at/above the complexity threshold when --gate-complexity is given.
    if args.fail_on_regression and delta.regressed:
        return 1
    if args.gate_complexity is not None and delta.high_complexity_new_or_regressed(args.gate_complexity):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sm", description="Shadow Mirror — semantic coverage.")
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("module", help="path to the source module")
        p.add_argument("--tests", required=True, help="path to the test target for that module")
        p.add_argument("--cwd", default=".", help="working directory for the test run (default: .)")
        p.add_argument("--lang", default="python",
                       choices=["python", "javascript", "typescript", "tsx"],
                       help="source language / adapter (default: python)")
        p.add_argument("--json", action="store_true", help="emit the canonical JSON")
        p.add_argument("--fail-on-gap", action="store_true", help="exit 1 if any level-gap is found")
        p.add_argument("-v", "--verbose", action="count", default=0,
                       help="-v: log per-node verdicts; -vv: per-mutant kill/survive (stderr)")

    m = sub.add_parser("map", help="map a module's five-level semantic coverage")
    _common(m)
    m.add_argument("--receipt", metavar="PATH", help="write a ReceiptV1 (SM-5) to PATH")
    m.add_argument("--bundle", metavar="PATH",
                   help="write a self-verifying EvidenceBundle (receipt + canonical map) to PATH")
    m.add_argument("--html", metavar="PATH", help="write a standalone HTML map view to PATH")
    m.set_defaults(func=_cmd_map)

    p = sub.add_parser("plan", help="rank a module's gaps + scaffold assertion stubs")
    _common(p)
    p.add_argument("--receipt", metavar="PATH", help="write a plan ReceiptV1 (SM-2) to PATH")
    p.add_argument("--diff", metavar="BASE",
                   help="scope the plan to nodes changed vs git ref BASE")
    p.add_argument("--brief", action="store_true",
                   help="emit a generation brief (acceptance contract + obligations) "
                        "instead of the plan")
    p.set_defaults(func=_cmd_plan)

    v = sub.add_parser("verify", help="verify candidate tests legitimately close gaps")
    v.add_argument("module", help="path to the Python module")
    v.add_argument("--tests", required=True, help="path to the baseline pytest suite")
    v.add_argument("--proposals", required=True, metavar="JSON",
                   help="proposals manifest: [{node_id, level, candidate (file), label?}]")
    v.add_argument("--cwd", default=".", help="working directory for the test run (default: .)")
    v.add_argument("--lang", default="python",
                   choices=["python", "javascript", "typescript", "tsx"],
                   help="source language / adapter (default: python)")
    v.add_argument("--json", action="store_true", help="emit the canonical JSON report")
    v.add_argument("-v", "--verbose", action="count", default=0,
                   help="-v: log per-node verdicts; -vv: per-mutant kill/survive (stderr)")
    v.add_argument("--receipt", metavar="PATH", help="write a verification ReceiptV1 (SM-5) to PATH")
    v.set_defaults(func=_cmd_verify)

    d = sub.add_parser("delta", help="compare two `sm map --json` outputs (base vs head)")
    d.add_argument("base", help="base map JSON (e.g. from the target branch)")
    d.add_argument("head", help="head map JSON (e.g. from the PR branch)")
    d.add_argument("--json", action="store_true", help="emit the canonical JSON delta")
    d.add_argument("--markdown", action="store_true",
                   help="emit a PR-comment-ready markdown delta (for CI annotation)")
    d.add_argument("--receipt", metavar="PATH", help="write a delta ReceiptV1 (SM-5) to PATH")
    d.add_argument("--fail-on-regression", action="store_true",
                   help="exit 1 if any proven cell regressed to a gap")
    d.add_argument("--gate-complexity", type=int, metavar="N",
                   help="exit 1 on a regression, or a new gap on a node with complexity >= N")
    d.set_defaults(func=_cmd_delta)

    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", 0))
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
