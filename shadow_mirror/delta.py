"""``sm delta`` — what a change did to semantic coverage (P6 surface).

Compares two maps (a *base* and a *head*, each a ``sm map --json`` payload) and
reports the cells that moved: gaps **closed**, proven cells that **regressed** to
gaps, and **new gaps** on nodes the change introduced. Pure dict comparison — no
subprocess, no git; CI produces the two maps (one per ref) and feeds them here.

This is the engine under two P6 surfaces: the PR annotation (the human-readable
delta a reviewer reads inline) and the optional gate (fail a PR that regresses a
proven cell, or adds a gap on a high-complexity node).

Node identity is the map's ``node_id`` (``path::qualname``); a renamed function
reads as one node removed + one added (R1 rename-tolerance is a later phase), so a
rename surfaces as *new gaps*, never a silent disappearance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .map import CoverageMap
from .receipt import ReceiptV1

__all__ = ["CellChange", "MapDelta", "build_delta"]


def _is_gap(verdict: str) -> bool:
    return verdict.startswith("gap")


@dataclass(frozen=True)
class CellChange:
    node_id: str
    level: str
    base_verdict: str | None  # None when the node is new in head
    head_verdict: str
    complexity: int  # head-side node complexity — what the gate thresholds on

    @property
    def qualname(self) -> str:
        return self.node_id.split("::")[-1]

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "level": self.level,
                "base": self.base_verdict, "head": self.head_verdict,
                "complexity": self.complexity}


def _cells(m: dict) -> dict[tuple[str, str], str]:
    return {(n["node_id"], lvl): v for n in m["nodes"] for lvl, v in n["levels"].items()}


def _complexity(m: dict) -> dict[str, int]:
    return {n["node_id"]: n["complexity"] for n in m["nodes"]}


@dataclass(frozen=True)
class MapDelta:
    module: str
    base_ref: str  # provenance: the two maps this delta derives from
    head_ref: str
    closed: tuple[CellChange, ...]  # base gap → head proven (improvement)
    regressed: tuple[CellChange, ...]  # base proven → head gap (a real loss)
    new_gaps: tuple[CellChange, ...]  # gap on a node that didn't exist in base

    def high_complexity_new_or_regressed(self, threshold: int) -> tuple[CellChange, ...]:
        """Regressions (any complexity) + new gaps on nodes at/above ``threshold`` —
        the gate set: a change that loses proof, or adds untested complex code."""
        return self.regressed + tuple(c for c in self.new_gaps if c.complexity >= threshold)

    def canonical_dict(self) -> dict:
        return {
            "module": self.module,
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "closed": [c.as_dict() for c in self.closed],
            "regressed": [c.as_dict() for c in self.regressed],
            "new_gaps": [c.as_dict() for c in self.new_gaps],
        }

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    def evidence_ref(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_receipt(self, ts: str) -> ReceiptV1:
        return ReceiptV1(
            phase="SM-5",
            hypothesis=f"semantic-coverage delta for {self.module}",
            instrumentation=("sm-delta",),
            assertion=f"{len(self.closed)} closed, {len(self.regressed)} regressed, "
                      f"{len(self.new_gaps)} new gap(s)",
            outcome="verified" if not self.regressed else "falsified",
            ts=ts,
            evidence_ref=self.evidence_ref(),
        )

    # Hidden marker so a CI workflow can find-and-update one sticky comment per PR
    # (grep for this line) instead of spamming a new comment on every push.
    MARKER = "<!-- shadow-mirror-delta -->"

    def to_markdown(self) -> str:
        """A PR-comment-ready GitHub-flavored-markdown delta. Regressions first
        (what a reviewer must see); closed last. Leads with the sticky marker."""
        out = [self.MARKER, "### Shadow Mirror — semantic-coverage delta", "",
               f"**{len(self.closed)} closed · {len(self.regressed)} regressed · "
               f"{len(self.new_gaps)} new gap(s)** — `{self.module}`", ""]
        if not (self.closed or self.regressed or self.new_gaps):
            out.append("_No semantic-coverage change._")
            return "\n".join(out)

        def table(title: str, cells: tuple[CellChange, ...]) -> None:
            if not cells:
                return
            out.extend([f"<details open><summary>{title} ({len(cells)})</summary>", "",
                        "| node / level | cx | base → head |", "|---|--:|---|"])
            for c in cells:
                base = c.base_verdict if c.base_verdict is not None else "_(new node)_"
                out.append(f"| `{c.qualname}/{c.level}` | {c.complexity} | "
                           f"{base} → {c.head_verdict} |")
            out.extend(["", "</details>", ""])
        table("✗ Regressed (proven → gap)", self.regressed)
        table("• New gaps", self.new_gaps)
        table("✓ Closed (gap → proven)", self.closed)
        return "\n".join(out).rstrip() + "\n"

    def to_text(self) -> str:
        rows = [f"sm delta — {self.module}",
                f"closed {len(self.closed)} · regressed {len(self.regressed)} · "
                f"new gap(s) {len(self.new_gaps)}", ""]

        def block(title: str, cells: tuple[CellChange, ...], arrow: str) -> None:
            if not cells:
                return
            rows.append(f"{title}:")
            for c in cells:
                base = c.base_verdict if c.base_verdict is not None else "(new node)"
                rows.append(f"  {c.qualname}/{c.level}  (cx {c.complexity})  "
                            f"{base} {arrow} {c.head_verdict}")
            rows.append("")
        block("✓ closed", self.closed, "→")
        block("✗ regressed", self.regressed, "→")
        block("• new gaps", self.new_gaps, "")
        if not (self.closed or self.regressed or self.new_gaps):
            rows.append("no semantic-coverage change.")
        return "\n".join(rows).rstrip()


def build_delta(base: CoverageMap | dict, head: CoverageMap | dict) -> MapDelta:
    """Compare ``base`` and ``head`` maps (objects or ``canonical_dict``s)."""
    bd = base.canonical_dict() if isinstance(base, CoverageMap) else base
    hd = head.canonical_dict() if isinstance(head, CoverageMap) else head
    base_cells, head_cells = _cells(bd), _cells(hd)
    head_cx = _complexity(hd)

    closed, regressed, new_gaps = [], [], []
    for key, hv in sorted(head_cells.items()):
        node_id, level = key
        cx = head_cx.get(node_id, 0)
        bv = base_cells.get(key)  # None ⇒ the node/level didn't exist in base
        if bv is not None and _is_gap(bv) and hv == "proven":
            closed.append(CellChange(node_id, level, bv, hv, cx))
        elif bv == "proven" and _is_gap(hv):
            regressed.append(CellChange(node_id, level, bv, hv, cx))
        elif _is_gap(hv) and (bv is None or (not _is_gap(bv) and bv != "proven")):
            # A gap in head where base was neither a gap nor proven — a node the
            # change *introduced* (bv None) OR an existing node that GAINED a gap
            # (n/a → an untested new raise/except). Both are "added a gap"; the gate
            # must see the second too, on existing complex nodes. bv None marks new.
            new_gaps.append(CellChange(node_id, level, bv, hv, cx))
    return MapDelta(module=hd["module"], base_ref=_ref(bd), head_ref=_ref(hd),
                    closed=tuple(closed), regressed=tuple(regressed), new_gaps=tuple(new_gaps))


def _ref(map_dict: dict) -> str:
    """A map dict's content-addressable ref (recomputed; canonical_json is stable)."""
    payload = json.dumps(map_dict, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
