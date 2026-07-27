"""Tests for the HTML map view (`render_html`) — pure string rendering, fast."""

from shadow_mirror.html import render_html
from shadow_mirror.map import NA, PROVEN, CoverageMap, LevelVerdict, MapNode
from shadow_mirror.resilient import GAP_UNASSERTED, GAP_UNEXERCISED

_LEVELS = ("functional", "behavioral", "performant", "resilient", "observable")


def _node(qualname, cx, **levels):
    lv = tuple(LevelVerdict(k, levels.get(k, NA), 0, 0) for k in _LEVELS)
    return MapNode(node_id=f"m.py::{qualname}", qualname=qualname, complexity=cx,
                   executed=True, levels=lv)


def _map(*nodes, module="m.py"):
    return CoverageMap(module=module, covered_lines=12, num_statements=20, nodes=nodes)


CM = _map(
    _node("charge", 2, functional=PROVEN, behavioral=GAP_UNASSERTED),
    _node("refund", 1, functional=GAP_UNEXERCISED))


def test_renders_self_contained_html_with_content():
    out = render_html(CM)
    assert out.startswith("<!doctype html>")
    assert "<style>" in out and "</html>" in out  # inline CSS, no external assets
    assert "http://" not in out and "https://" not in out  # zero external refs
    assert "charge" in out and "refund" in out
    assert "line coverage (coverage.py):\n12/20" in out or "12/20" in out


def test_verdict_glyphs_and_classes_present():
    out = render_html(CM)
    assert "✓" in out and "▲" in out and "·" in out  # proven / gap / unexercised
    assert 'class="cell proven"' in out and 'class="cell gap"' in out
    assert "1 level-gap(s)" in out or "level-gap(s)" in out  # gaps summary block


def test_escapes_interpolated_names():
    cm = _map(_node("ev<il> & co", 1, functional=PROVEN), module="a<b>.py")
    out = render_html(cm)
    assert "ev&lt;il&gt; &amp; co" in out
    assert "a&lt;b&gt;.py" in out
    assert "<il>" not in out  # raw angle brackets from the name never leak


def test_deterministic_no_timestamp():
    assert render_html(CM) == render_html(CM)  # no embedded clock → byte-identical


def test_no_gaps_renders_clean_state():
    clean = _map(_node("ok", 1, functional=PROVEN))
    assert "no gaps" in render_html(clean)
