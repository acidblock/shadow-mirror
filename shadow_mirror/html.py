"""``sm map --html`` — render a :class:`~shadow_mirror.map.CoverageMap` as a
standalone HTML page.

Pure: ``CoverageMap -> HTML`` string, stdlib only — no runtime dependency, no
external JS/CSS, and **no embedded timestamp**, so the output is deterministic and
testable (the same discipline that bans ``Date.now()`` in generated artifacts).
All interpolated names are ``html.escape``-d.
"""

from __future__ import annotations

import html

from .map import LEVELS, CoverageMap
from .resilient import GAP_UNASSERTED, GAP_UNEXERCISED, NO_SIGNAL, PROVEN

NA = "n/a"

__all__ = ["render_html"]

# verdict -> (glyph, human label, css class)
_CELL = {
    PROVEN: ("✓", "proven", "proven"),
    GAP_UNASSERTED: ("▲", "gap — runs, unasserted", "gap"),
    GAP_UNEXERCISED: ("·", "gap — never runs", "unexercised"),
    NA: ("–", "n/a", "na"),
    NO_SIGNAL: ("?", "no signal", "nosignal"),
}

_STYLE = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; margin: 2rem; }
h1 { font-size: 1.1rem; margin: 0 0 .2rem; }
.sub { color: #888; margin: 0 0 1.2rem; }
table { border-collapse: collapse; }
th, td { padding: .35rem .6rem; text-align: center; border-bottom: 1px solid #8884; }
th.fn, td.fn { text-align: left; }
td.cx { color: #888; }
.cell { font-weight: 700; border-radius: 4px; }
.proven { color: #1a7f37; }
.gap { color: #9a6700; background: #fff3cd44; }
.unexercised { color: #888; }
.na { color: #ccc; }
.nosignal { color: #cf222e; }
.legend { margin-top: 1.2rem; color: #888; }
.legend span { margin-right: 1.2rem; white-space: nowrap; }
.gaps { margin-top: 1rem; }
""".strip()


def _row(node) -> str:
    cells = {lv.level: lv.verdict for lv in node.levels}
    tds = [f'<td class="fn">{html.escape(node.qualname)}</td>',
           f'<td class="cx">{node.complexity}</td>']
    for level in LEVELS:
        glyph, label, klass = _CELL.get(cells.get(level, NA), ("?", "no signal", "nosignal"))
        tds.append(f'<td class="cell {klass}" title="{html.escape(label)}">{glyph}</td>')
    return "    <tr>" + "".join(tds) + "</tr>"


def render_html(cmap: CoverageMap) -> str:
    """Render ``cmap`` as a self-contained HTML page. Deterministic."""
    head = ("".join(f"<th>{html.escape(lv[:4])}</th>" for lv in LEVELS))
    rows = "\n".join(_row(n) for n in sorted(cmap.nodes, key=lambda n: n.node_id))
    gaps = cmap.gaps()
    gap_items = "".join(
        f"<li>{html.escape(q.split('::')[-1])}/{html.escape(lvl)} "
        f"<em>({html.escape(v)})</em></li>" for q, lvl, v in gaps)
    gaps_block = (f'<div class="gaps"><strong>{len(gaps)} level-gap(s)</strong>'
                  f"<ul>{gap_items}</ul></div>" if gaps else
                  '<div class="gaps"><strong>no gaps</strong></div>')
    legend = "".join(
        f'<span class="cell {k}">{g}</span> {html.escape(lbl)}'
        for g, lbl, k in (_CELL[v] for v in (PROVEN, GAP_UNASSERTED, GAP_UNEXERCISED, NA)))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>sm map — {html.escape(cmap.module)}</title>
<style>{_STYLE}</style></head>
<body>
<h1>Shadow Mirror — semantic coverage</h1>
<p class="sub">{html.escape(cmap.module)} · line coverage (coverage.py):
{cmap.covered_lines}/{cmap.num_statements}</p>
<table>
  <thead><tr><th class="fn">function</th><th>cx</th>{head}</tr></thead>
  <tbody>
{rows}
  </tbody>
</table>
<div class="legend"><span></span>{legend}</div>
{gaps_block}
</body></html>
"""
