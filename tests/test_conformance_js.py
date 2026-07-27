"""Cross-language conformance: the JsAdapter AND TsAdapter maps match Python GROUND TRUTH.

P7's success criterion — identical map/gap-map *semantics* across languages. The
fixtures are equivalent (``tests/fixtures/resilient_demo/orders.py`` and its JS
mirror ``conformance_js/orders.js`` + TS mirror ``conformance_js/ts/orders.ts``,
same functions, same test strengths). Conformance is keyed on
``(qualname-via-correspondence, level) -> verdict``; node_id and shape_hash are NOT
cross-language keys (different grammars). TS uses the same camelCase names as JS, so
the same CORRESPONDENCE / GROUND_TRUTH dicts anchor both.

Anchored to GROUND TRUTH, not adapter-vs-adapter: the expected verdicts are the
ones ``tests/test_map.py`` already asserts for the Python fixture (independently
known-correct), so this adds exactly "JS/TS matches known-correct" and is immune to
two-adapters-wrong-the-same-way. JS≡Python and TS≡Python together give TS≡JS.

The TS mirror reuses the JS fixture's ``node_modules`` (vitest resolves it upward
from the ``ts/`` subdir; esbuild transpiles ``.ts``), so no second ``npm ci``. The
source-map round-trip that makes this sound is spiked: docs/spikes/P7-typescript-spike.md.

Skips (never fails) when a toolchain is absent — the base Python suite runs without
node. Marked slow: a full map runs many ``vitest`` subprocesses.
"""

import os
import shutil

import pytest

# SM_REQUIRE_JS=1 (set in CI) turns every "toolchain missing -> skip" into a hard
# FAILURE, so a missing tree-sitter wheel / `npm ci` / node turns CI red instead of
# green-with-skips. A skip-guarded conformance suite that only runs where someone
# hand-installed deps is a demo, not a gate — this makes the P7 deliverable enforced.
_REQUIRE = bool(os.environ.get("SM_REQUIRE_JS"))

if _REQUIRE:
    import tree_sitter  # noqa: F401  -- ImportError here = CI red, by design
    import tree_sitter_javascript  # noqa: F401
    import tree_sitter_typescript  # noqa: F401  -- the [ts] extra; CI red if missing
else:
    pytest.importorskip("tree_sitter", reason="JsAdapter needs the [js] extra (tree-sitter)")
    pytest.importorskip("tree_sitter_javascript", reason="JsAdapter needs tree-sitter-javascript")
    # tree-sitter-typescript is checked per-TS-fixture so a [js]-only local install
    # still runs the JS conformance.

pytestmark = pytest.mark.slow

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "tests" / "fixtures" / "conformance_js"

# snake_case (Python) <-> camelCase (JS): declared, not silently renamed.
CORRESPONDENCE = {
    "apply_discount": "applyDiscount",
    "charge": "charge",
    "charge_async": "chargeAsync",
    "line_total": "lineTotal",
    "slow_double": "slowDouble",
    "validate_sku": "validateSku",
    "refund": "refund",
    "normalize_qty": "normalizeQty",
}

# Python ground truth — the verdicts tests/test_map.py independently asserts for
# tests/fixtures/resilient_demo/orders.py. (level, py_qualname) -> verdict.
GROUND_TRUTH = {
    ("functional", "apply_discount"): "proven",
    ("functional", "charge"): "gap-unexercised",
    ("functional", "line_total"): "proven",
    # behavioral + performant also conform on the asserted nodes (spine carried them):
    ("behavioral", "charge"): "proven",
    ("behavioral", "line_total"): "proven",
    # gap-unasserted is the one class that proves run_selected ran the covering
    # tests AND they survived (not a vacuous zero-match exit-0). apply_discount's
    # weak value-blind test leaves the arithmetic swap unkilled.
    ("behavioral", "apply_discount"): "gap-unasserted",
    ("performant", "slow_double"): "proven",
    # resilient: throw-type-swap (the implemented operator) conforms on 3 of 4
    # asserted nodes. refund=gap-unexercised guards the coverage() innermost-owner
    # fix (a compound `if` must not mark its never-thrown `throw` executed).
    # normalizeQty is the one genuine divergence (Python proven via except-body
    # mutation; JS catch-recovery + instanceof-routing operators are the next slice).
    ("resilient", "refund"): "gap-unexercised",
    ("resilient", "validate_sku"): "proven",
    # async throw asserted via the promise form (`await ...rejects.toThrow(Type)`).
    # Same throw-type-swap operator, same verdict as the sync type-pin — the
    # async/promise form is a clean CONFORMANCE row, not a divergence (unlike the
    # deferred instanceof-routing operator, which Python's resilient level lacks).
    ("resilient", "charge_async"): "proven",
    ("resilient", "apply_discount"): "gap-unasserted",
    # catch-recovery-neutralize (the second resilient operator) closes the last
    # divergence: normalizeQty's except-recovery (return 0) is pinned by `=== 0`,
    # so perturbing the recovered constant kills it -> proven, matching Python.
    ("resilient", "normalize_qty"): "proven",
}


def _skip_if_no_toolchain():
    missing = None
    if shutil.which("npx") is None:
        missing = "npx/vitest not available"
    elif not (JS_DIR / "node_modules" / "vitest").exists():
        missing = "vitest not installed in the fixture (run `npm ci` in conformance_js)"
    if missing:
        if _REQUIRE:
            pytest.fail(f"SM_REQUIRE_JS is set but {missing} — CI must install the JS toolchain")
        pytest.skip(missing)


def _skip_if_no_ts():
    # TS reuses the JS toolchain (same vitest/node_modules); it adds only the
    # tree-sitter-typescript grammar. Under SM_REQUIRE_JS that grammar is imported
    # at module load (CI red if missing); locally it may be a [js]-only install.
    _skip_if_no_toolchain()
    if not _REQUIRE:
        pytest.importorskip("tree_sitter_typescript", reason="TsAdapter needs the [ts] extra")


def _build_levels(adapter, module: str, tests: str, base=None) -> dict:
    import os

    from shadow_mirror.map import build_full_map

    # The engine assumes the process cwd is the project root (mutated_file overlays
    # the module relative to it, and the test runner reads it there); mcp_tools._at
    # does the same chdir. Mirror that: chdir to the project for the build. ``base``
    # defaults to JS_DIR; the TS mirror (``ts/``) and the inherit fixture
    # (``inherit/``) are subdirs that reuse this project's node_modules.
    base = base or JS_DIR
    prev = os.getcwd()
    try:
        os.chdir(base)
        m = build_full_map(module, tests, cwd=str(base), adapter=adapter)
    finally:
        os.chdir(prev)
    return {n.qualname: {lv.level: lv.verdict for lv in n.levels} for n in m.nodes}


def _js_adapter():
    from shadow_mirror.adapters.javascript import JsAdapter

    return JsAdapter()


def _ts_adapter():
    from shadow_mirror.adapters.typescript import TsAdapter

    return TsAdapter()


@pytest.fixture(scope="module")
def js_levels():
    _skip_if_no_toolchain()
    return _build_levels(_js_adapter(), "orders.js", "orders.test.js")


@pytest.fixture(scope="module")
def service_levels():
    _skip_if_no_toolchain()
    return _build_levels(_js_adapter(), "service.js", "service.test.js")


@pytest.fixture(scope="module")
def ts_levels():
    _skip_if_no_ts()
    return _build_levels(_ts_adapter(), "ts/orders.ts", "ts/orders.test.ts")


@pytest.fixture(scope="module")
def ts_service_levels():
    _skip_if_no_ts()
    return _build_levels(_ts_adapter(), "ts/service.ts", "ts/service.test.ts")


@pytest.mark.parametrize("level,py_name", list(GROUND_TRUTH))
def test_js_verdict_matches_python_ground_truth(js_levels, level, py_name):
    js_name = CORRESPONDENCE[py_name]
    assert js_name in js_levels, f"JS map missing {js_name}"
    assert js_levels[js_name][level] == GROUND_TRUTH[(level, py_name)], (
        f"{js_name}.{level}: JS={js_levels[js_name][level]!r} != "
        f"Python ground truth {GROUND_TRUTH[(level, py_name)]!r}"
    )


def test_js_discovers_all_functions(js_levels):
    # Sanity: the adapter found every function the fixture exports.
    assert set(js_levels) == {
        "normalizeQty", "applyDiscount", "charge", "chargeAsync", "refund",
        "validateSku", "lineTotal", "slowDouble",
    }


# TS conformance — the TsAdapter map matches the SAME Python ground truth as JS, with
# type annotations present on every node the operators target (params, return types).
# TS names == JS camelCase, so CORRESPONDENCE / GROUND_TRUTH are reused verbatim.
@pytest.mark.parametrize("level,py_name", list(GROUND_TRUTH))
def test_ts_verdict_matches_python_ground_truth(ts_levels, level, py_name):
    ts_name = CORRESPONDENCE[py_name]
    assert ts_name in ts_levels, f"TS map missing {ts_name}"
    assert ts_levels[ts_name][level] == GROUND_TRUTH[(level, py_name)], (
        f"{ts_name}.{level}: TS={ts_levels[ts_name][level]!r} != "
        f"Python ground truth {GROUND_TRUTH[(level, py_name)]!r}"
    )


def test_ts_discovers_all_functions(ts_levels):
    assert set(ts_levels) == {
        "normalizeQty", "applyDiscount", "charge", "chargeAsync", "refund",
        "validateSku", "lineTotal", "slowDouble",
    }


def test_adapter_toolchains_are_language_correct():
    # Cheap (no map build): the receipt provenance must name the real language +
    # grammar with versions — a JS/TS/TSX run must NOT claim Python's "coverage.py".
    cases = {
        "javascript": (_js_adapter(), "tree-sitter-javascript"),
        "typescript": (_ts_adapter(), "tree-sitter-typescript"),
        "tsx": (_tsx_adapter(), "tree-sitter-typescript"),
    }
    for lang, (adapter, grammar_pkg) in cases.items():
        tc = adapter.toolchain()
        assert tc[0] == lang  # language-correct, first element
        assert any(t.startswith(f"{grammar_pkg}@") for t in tc)  # versioned grammar
        assert not any("coverage.py" in t for t in tc)  # never the Python tool


# Observable conformance — service.js mirrors tests/fixtures/observable_demo/service.py,
# whose verdicts tests/test_map.py::test_observable_discriminates asserts. console.* is
# the emit surface (stdlib-logging analog); vi.spyOn is the caplog analog.
OBSERVABLE_CORRESPONDENCE = {
    "record_purchase": "recordPurchase",
    "compute_tax": "computeTax",
    "escalate": "escalate",
    "add": "add",
}
OBSERVABLE_GROUND_TRUTH = {
    "record_purchase": "proven",          # spy asserts the emit
    "compute_tax": "gap-unasserted",      # emit runs, unobserved
    "escalate": "gap-unexercised",        # emit behind a branch no test takes
    "add": "n/a",                         # no emit
}


@pytest.mark.parametrize("py_name", list(OBSERVABLE_GROUND_TRUTH))
def test_js_observable_matches_python_ground_truth(service_levels, py_name):
    js_name = OBSERVABLE_CORRESPONDENCE[py_name]
    assert js_name in service_levels, f"JS map missing {js_name}"
    assert service_levels[js_name]["observable"] == OBSERVABLE_GROUND_TRUTH[py_name], (
        f"{js_name}.observable: JS={service_levels[js_name]['observable']!r} != "
        f"Python ground truth {OBSERVABLE_GROUND_TRUTH[py_name]!r}"
    )


@pytest.mark.parametrize("py_name", list(OBSERVABLE_GROUND_TRUTH))
def test_ts_observable_matches_python_ground_truth(ts_service_levels, py_name):
    ts_name = OBSERVABLE_CORRESPONDENCE[py_name]
    assert ts_name in ts_service_levels, f"TS map missing {ts_name}"
    assert ts_service_levels[ts_name]["observable"] == OBSERVABLE_GROUND_TRUTH[py_name], (
        f"{ts_name}.observable: TS={ts_service_levels[ts_name]['observable']!r} != "
        f"Python ground truth {OBSERVABLE_GROUND_TRUTH[py_name]!r}"
    )


# Build slice 1 (P7-tsx-jsx-spike.md): coverage() must INHERIT the target project's
# vitest config rather than replace it, so a DOM `environment` + the project's
# `setupFiles` survive (the .tsx render need). The fixture lives in its own subdir
# (its vitest.config.ts sets environment: happy-dom + a marker setupFile) so it does
# NOT bleed into orders/service, which have no target config and exercise the
# unchanged standalone path. This test therefore carries the entire merge-path
# coverage; conformance keeps guarding the unchanged no-target path.
INHERIT_DIR = JS_DIR / "inherit"


def _skip_if_no_happy_dom():
    if not (JS_DIR / "node_modules" / "happy-dom").exists():
        missing = "happy-dom not installed (run `npm ci` in conformance_js)"
        if _REQUIRE:
            pytest.fail(f"SM_REQUIRE_JS is set but {missing}")
        pytest.skip(missing)


def test_ts_coverage_inherits_target_vitest_config():
    _skip_if_no_ts()
    _skip_if_no_happy_dom()
    levels = _build_levels(_ts_adapter(), "calc.ts", "calc.test.ts", base=INHERIT_DIR)
    # `dbl`'s single covering test asserts `document` (needs the inherited
    # environment), the marker global (needs the inherited setupFiles), AND pins the
    # arithmetic (needs intact per-test attribution). So behavioral=proven proves all
    # three were inherited by the merge. Without the merge the covering test throws on
    # `document` and no coverage is produced — build_full_map raises — so this test
    # fails loud rather than silently degrading. (Verified: forcing the standalone
    # path makes this path error.)
    assert levels["dbl"]["behavioral"] == "proven", (
        f"coverage() did not inherit the target vitest config — dbl behavioral is "
        f"{levels['dbl']['behavioral']!r}, expected 'proven'"
    )


# Build slice 2 (P7-tsx-jsx-spike.md): the .tsx grammar binding (TsxAdapter) + a
# Preact component-RENDER fixture, unblocked by slice 1's config inheritance. The
# fixture's vitest.config.ts sets environment: happy-dom + the esbuild JSX transform
# (a config-root sibling of test:, which coverage() now inherits). Isolated subdir so
# it does not affect the other conformance runs.
TSX_DIR = JS_DIR / "tsx"


def _tsx_adapter():
    from shadow_mirror.adapters.tsx import TsxAdapter

    return TsxAdapter()


def _skip_if_no_preact():
    if not (JS_DIR / "node_modules" / "preact").exists():
        missing = "preact not installed (run `npm ci` in conformance_js)"
        if _REQUIRE:
            pytest.fail(f"SM_REQUIRE_JS is set but {missing}")
        pytest.skip(missing)


def test_tsx_component_render_verdicts():
    # Direct assertion, not a Python mirror: the verdict LOGIC is shared with
    # TsAdapter and already Python-anchored by the conformance suite above, so a TSX
    # mirror would only re-prove the proven path. This targets what is NEW — JSX
    # parsing (the language_tsx grammar) + render attribution through the inherited
    # DOM environment. The rigor that replaces the Python anchor is DISCRIMINATION:
    # Badge.behavioral=proven (a render test pins {n*2}) vs Loose.behavioral=gap
    # (a value-blind render test) proves attribution actually reached the
    # JSX-embedded site rather than uniformly degrading on empty attribution.
    _skip_if_no_ts()
    _skip_if_no_happy_dom()
    _skip_if_no_preact()
    lv = _build_levels(_tsx_adapter(), "components.tsx", "components.test.tsx", base=TSX_DIR)
    assert lv["Badge"]["functional"] == "proven"  # return <jsx> -> null, caught by the render
    assert lv["Badge"]["behavioral"] == "proven"  # render test pins n*2
    assert lv["Loose"]["behavioral"] == "gap-unasserted"  # value-blind -> *→/ survives (discrimination)
    assert lv["Logged"]["observable"] == "proven"  # spy asserts the emit; nullify -> killed
