"""Shared tree-sitter adapter base (P7): JS and TS differ only by *grammar*.

The JS adapter assembled the six P7 spikes into a working :class:`LanguageAdapter`
(tree-sitter + Istanbul + vitest). TypeScript is a documented grammar *superset* —
``function_declaration`` / ``throw_statement`` / ``catch_clause`` /
``binary_expression`` / ``new_expression`` and their fields are identically named,
and the extra type-annotation nodes are simply never matched by the site-finders
(verified against ``tree-sitter-typescript`` before this extraction; see
``docs/spikes/P7-typescript-spike.md``). The vitest-facing methods (coverage / run /
apply) shell out to ``npx vitest``, which handles ``.ts`` natively. So *everything
here is grammar-agnostic except the parser* — this base takes the grammar as a
constructor argument, and ``JsAdapter`` / ``TsAdapter`` are thin bindings.

This module imports only ``tree_sitter`` (the base library), NOT a specific grammar
package — so the ``[js]`` and ``[ts]`` extras stay independent (importing the JS
adapter does not require ``tree-sitter-typescript`` and vice versa — C1).

Spike provenance: per-test attribution via ``__VITEST_COVERAGE__`` snapshot-diff
(P7-vitest-coverage / P7-node-mapping); byte-splice mutation + ``has_error`` guard
(P7-js-mutation); inline-timing detection (P7-performant); source-map round-trip
for ``.ts`` (P7-typescript).
"""

from __future__ import annotations

import hashlib
import importlib.metadata as _md
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Collection
from contextlib import AbstractContextManager
from pathlib import Path

from tree_sitter import Language, Parser

from .._run import mutated_file  # language-agnostic text overlay (flock + recovery)
from .._version import __version__ as _SM_VERSION
from ..spi import Coverage, ErrorBranch, FunctionNode, ModuleModel, Mutant, TestId

# language -> the tree-sitter grammar package that backs it (for toolchain versions).
_GRAMMAR_PKG = {
    "javascript": "tree-sitter-javascript",
    "typescript": "tree-sitter-typescript",
    "tsx": "tree-sitter-typescript",
}


def _pkg_version(name: str) -> str:
    try:
        return _md.version(name)
    except _md.PackageNotFoundError:  # pragma: no cover - defensive
        return "unknown"

# Behavioral operator-swap table (JS/TS spelling) — for the behavioral level.
_SWAP = {"+": "-", "-": "+", "*": "/", "/": "*", "%": "*",
         "<": ">=", ">": "<=", "<=": ">", ">=": "<", "===": "!==", "!==": "===",
         "==": "!=", "!=": "==", "&&": "||", "||": "&&"}
_DECISION = {"if_statement", "for_statement", "for_in_statement", "while_statement",
             "do_statement", "ternary_expression", "catch_clause", "switch_case"}
_EMIT_METHODS = frozenset({"log", "info", "warn", "error", "debug", "trace", "exception"})
_LOGGER_NAMES = frozenset({"console", "logger", "log", "logging"})
_TIMING = frozenset({"now", "measure", "mark"})  # performance.<...> — perf_counter analog


def _walk(node):
    yield node
    for c in node.children:
        yield from _walk(c)


def _text(source_bytes: bytes, node) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


def _line(node) -> int:
    return node.start_point[0] + 1  # tree-sitter 0-based row -> 1-based line (node-mapping spike)


def _shape_hash(source_bytes: bytes, node) -> str:
    # Normalized, line-number-free structural fingerprint (core SHAPE_HASH_CONTRACT):
    # the pre-order sequence of node types, which carries no positions or formatting.
    types = "".join(n.type for n in _walk(node))
    return hashlib.sha256(types.encode("utf-8")).hexdigest()[:16]


# --- function / branch discovery ---------------------------------------------

_FN_TYPES = {"function_declaration", "method_definition", "function_expression",
             "arrow_function", "generator_function_declaration"}


def _fn_name(sb: bytes, node) -> str:
    nm = node.child_by_field_name("name")
    return _text(sb, nm) if nm else "<anonymous>"


def _complexity(node) -> int:
    score = 1
    for n in _walk(node):
        if n.type in _DECISION:
            score += 1
        elif n.type == "binary_expression":
            op = n.child_by_field_name("operator")
            if op and op.type in ("&&", "||"):
                score += 1
    return score


def _return_lines(sb: bytes, fn_body) -> tuple[int, ...]:
    out = []
    for n in _walk(fn_body):
        if n.type == "return_statement":
            val = n.children[1] if len(n.children) > 1 and n.children[1].is_named else None
            if val is not None and _text(sb, val) not in ("null", "undefined"):
                out.append(_line(n))
    return tuple(out)


class _TreeSitterAdapter:
    """Shared :class:`shadow_mirror.spi.LanguageAdapter` for tree-sitter languages.

    Parameterized by grammar: ``language`` is the receipt label
    (``"javascript"`` / ``"typescript"``), ``ts_language`` is the
    ``tree_sitter.Language``-compatible grammar capsule. Subclasses bind a concrete
    grammar in ``__init__`` (see ``javascript.py`` / ``typescript.py``)."""

    def __init__(self, language: str, ts_language):
        self.language = language
        self._parser = Parser(Language(ts_language))

    def _parse(self, source: str):
        return self._parser.parse(source.encode("utf-8"))

    # --- discover -------------------------------------------------------------

    def discover(self, source: str, module_path: str) -> ModuleModel:
        sb = source.encode("utf-8")
        root = self._parse(source).root_node
        functions: list[FunctionNode] = []
        branches: list[ErrorBranch] = []
        counters: dict[tuple[str, str], int] = {}

        for node in _walk(root):
            if node.type in _FN_TYPES and node.child_by_field_name("name"):
                name = _fn_name(sb, node)
                body = node.child_by_field_name("body") or node
                functions.append(FunctionNode(
                    node_id=f"{module_path}::{name}",
                    qualname=name,
                    lineno=_line(node),
                    end_lineno=node.end_point[0] + 1,
                    complexity=_complexity(node),
                    return_lines=_return_lines(sb, body),
                    has_error_branches=any(n.type in ("throw_statement", "catch_clause")
                                           for n in _walk(node)),
                    shape_hash=_shape_hash(sb, node),
                ))

        # error branches: throw_statement ("throw") and catch_clause ("except")
        for node in _walk(root):
            kind = {"throw_statement": "throw", "catch_clause": "except"}.get(node.type)
            if kind is None:
                continue
            qual = _enclosing_fn(sb, node, root)
            key = (qual, kind)
            ordinal = counters.get(key, 0)
            counters[key] = ordinal + 1
            branches.append(ErrorBranch(
                node_id=f"{module_path}::{qual}#{kind}:{ordinal}",
                kind=kind,
                qualname=qual,
                exc_type=_thrown_type(sb, node),
                lineno=_line(node),
                end_lineno=node.end_point[0] + 1,
                body_lines=(_line(node), node.end_point[0] + 1),
                shape_hash=_shape_hash(sb, node),
            ))
        return ModuleModel(path=module_path, functions=tuple(functions), branches=tuple(branches))

    # --- coverage (the integration risk concentrator) -------------------------

    def coverage(self, module_path: str, tests_path: str, cwd: str) -> Coverage:
        # The injected config + setup must live INSIDE the project root so that
        # `vitest/config` and the `vitest` setup import resolve against the target's
        # node_modules (a /tmp config cannot — ERR_MODULE_NOT_FOUND). Written with a
        # pid-unique name and removed in `finally` (transient, like mutated_file).
        tag = f".sm-{os.getpid()}"
        setup = Path(cwd) / f"{tag}-setup.mjs"
        config = Path(cwd) / f"{tag}-vitest.config.mjs"
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "attrib.jsonl"
            covdir = Path(tmp) / "cov"
            log.write_text("", encoding="utf-8")  # adapter truncates; setup only appends
            setup.write_text(_SETUP_JS, encoding="utf-8")
            # Inherit the target project's vitest/vite config if present (else a
            # byte-identical standalone block) — preserves environment / setupFiles
            # / plugins / jsx that component (.tsx) tests need.
            target = _find_target_config(cwd)
            config.write_text(_config_js(setup.name, module_path, covdir, target), encoding="utf-8")
            env = {**os.environ, "SM_ATTRIB_LOG": str(log)}
            try:
                subprocess.run(
                    ["npx", "vitest", "run", tests_path, "--config", config.name, "--coverage"],
                    cwd=cwd, capture_output=True, text=True, env=env,
                )
                report = json.loads((covdir / "coverage-final.json").read_text(encoding="utf-8"))
            finally:
                setup.unlink(missing_ok=True)
                config.unlink(missing_ok=True)
            entry = _match_entry(report, module_path, cwd)
            owner, owned = _line_ownership(entry["statementMap"])
            # A line is executed iff its OWNING (smallest-span) statement ran. Full
            # start..end span still reaches continuation lines (the node-mapping
            # trap), but a compound statement's span no longer over-marks an
            # un-executed inner line — e.g. an `if` that ran does not mark its
            # never-thrown `throw` executed. Matches coverage.py's line precision.
            executed = {ln for ln, s in owner.items() if entry["s"][s] > 0}
            line_tests: dict[int, set[TestId]] = {}
            for rec in (json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()):
                tid = f"{rec['file']}::{rec['name']}"
                for s in rec["s"]:
                    for ln in owned.get(s, ()):
                        line_tests.setdefault(ln, set()).add(tid)
        num = len(entry["statementMap"])
        return Coverage(
            covered=sum(1 for h in entry["s"].values() if h > 0),
            num_statements=num,
            executed_lines=frozenset(executed),
            line_tests={ln: frozenset(t) for ln, t in line_tests.items()},
        )

    # --- mutants --------------------------------------------------------------

    def mutants(self, level: str, source: str, node: FunctionNode | ErrorBranch) -> tuple[Mutant, ...]:
        sb = source.encode("utf-8")
        if level == "functional":
            return self._splice_mutants(sb, source, node, _functional_sites)
        if level == "behavioral":
            return self._splice_mutants(sb, source, node, _behavioral_sites)
        if level == "observable":
            return self._splice_mutants(sb, source, node, _observable_sites)
        if level == "resilient":
            return self._splice_mutants(sb, source, node, _resilient_sites)
        return ()

    def _splice_mutants(self, sb, source, fnode, site_fn) -> tuple[Mutant, ...]:
        out: list[Mutant] = []
        for label, a, b, rep, lineno in site_fn(self._parse, sb, source, fnode):
            mutant = sb[:a] + rep + sb[b:]
            if self._parse(mutant.decode("utf-8")).root_node.has_error:
                continue  # well-formedness guard (false-kill trap)
            out.append(Mutant(label=label, mutated_source=mutant.decode("utf-8"), lineno=lineno))
        return tuple(out)

    # --- detection / running / apply ------------------------------------------

    def timing_tests(self, tests_path: str, cwd: str) -> frozenset[TestId]:
        src = (Path(cwd) / tests_path).read_text(encoding="utf-8")
        sb = src.encode("utf-8")
        root = self._parse(src).root_node
        out: set[TestId] = set()
        for call in _walk(root):
            if call.type != "call_expression":
                continue
            fn = call.child_by_field_name("function")
            args = call.child_by_field_name("arguments")
            if not fn or _text(sb, fn) != "test" or not args:
                continue
            named = [c for c in args.children if c.is_named]
            if not named:
                continue
            tname = _str_literal(sb, named[0])
            body = named[1] if len(named) > 1 else None
            if body and _has_timing(sb, body):
                out.add(f"{tests_path}::{tname}")
        return frozenset(out)

    def run_all(self, tests_path: str, cwd: str) -> int:
        r = subprocess.run(["npx", "vitest", "run", tests_path, "--no-coverage"],
                           cwd=cwd, capture_output=True, text=True)
        return r.returncode

    def run_selected(self, test_ids: Collection[TestId], cwd: str) -> int:
        by_file: dict[str, list[str]] = {}
        for tid in test_ids:
            f, _, name = tid.partition("::")
            by_file.setdefault(f, []).append(name)
        code = 0
        for f, names in by_file.items():
            pat = "^(" + "|".join(re.escape(n) for n in names) + ")$"
            r = subprocess.run(["npx", "vitest", "run", f, "-t", pat, "--no-coverage"],
                               cwd=cwd, capture_output=True, text=True)
            code = code or r.returncode
        return code

    def apply(self, module_path: str, mutated_source: str) -> AbstractContextManager[None]:
        return mutated_file(module_path, mutated_source)  # text overlay is language-agnostic

    def toolchain(self) -> tuple[str, ...]:
        grammar = _GRAMMAR_PKG[self.language]
        # tree-sitter (parse) versions are in-process; vitest + istanbul run
        # out-of-process in the target's node_modules, so they are named but not
        # version-pinned here (their version is the target project's, not ours).
        return (
            self.language,
            f"tree-sitter@{_pkg_version('tree-sitter')}",
            f"{grammar}@{_pkg_version(grammar)}",
            "vitest+istanbul(out-of-process)",
            f"sm-mutation@{_SM_VERSION}",
        )


# --- module-level helpers (grammar-agnostic — operate on parsed nodes) -------


def _enclosing_fn(sb: bytes, node, root) -> str:
    cur = node.parent
    while cur is not None:
        if cur.type in _FN_TYPES and cur.child_by_field_name("name"):
            return _fn_name(sb, cur)
        cur = cur.parent
    return "<module>"


def _thrown_type(sb: bytes, node) -> str | None:
    if node.type == "throw_statement":
        for n in _walk(node):
            if n.type == "new_expression":
                ctor = n.child_by_field_name("constructor")
                return _text(sb, ctor) if ctor else None
    return None


def _str_literal(sb: bytes, node) -> str:
    t = _text(sb, node)
    return t[1:-1] if len(t) >= 2 and t[0] in "\"'`" else t


def _has_timing(sb: bytes, node) -> bool:
    for m in _walk(node):
        if m.type == "member_expression":
            obj, prop = m.child_by_field_name("object"), m.child_by_field_name("property")
            if obj and prop and _text(sb, obj) == "performance" and _text(sb, prop) in _TIMING:
                return True
    return False


def _line_ownership(statement_map: dict) -> tuple[dict[int, str], dict[str, set[int]]]:
    """Assign each source line to the SMALLEST-span statement covering it.

    Returns ``(owner: line -> s_index, owned: s_index -> {lines})``. Full
    start..end spans still reach continuation lines (node-mapping spike), but a
    compound statement (``if``/``try``/``for``) whose span overlaps an inner
    statement's own s-index does not claim that inner line — the inner statement,
    having the smaller span, owns it. This makes ``executed`` line-precise like
    coverage.py instead of over-marking un-executed inner lines.
    """
    owner: dict[int, tuple[int, str]] = {}  # line -> (span_size, s_index)
    for s, v in statement_map.items():
        start, end = v["start"]["line"], v["end"]["line"]
        size = end - start
        for ln in range(start, end + 1):
            if ln not in owner or size < owner[ln][0]:
                owner[ln] = (size, s)
    owned: dict[str, set[int]] = {}
    for ln, (_size, s) in owner.items():
        owned.setdefault(s, set()).add(ln)
    return {ln: s for ln, (_sz, s) in owner.items()}, owned


def _match_entry(report: dict, module_path: str, cwd: str) -> dict:
    want = (Path(cwd) / module_path).resolve()
    for key, entry in report.items():
        try:
            if Path(key).resolve() == want or Path(key).name == want.name:
                return entry
        except OSError:  # pragma: no cover - defensive
            continue
    raise KeyError(f"{module_path} not in coverage report ({list(report)})")


# --- mutation site finders (return (label, start_byte, end_byte, replacement, lineno)) ---
#
# Each takes ``parse`` (the adapter's grammar-bound parser) as its first arg so the
# site-finding is grammar-correct for JS or TS without a module global.


def _fn_range(fnode):
    return fnode.lineno, fnode.end_lineno


def _functional_sites(parse, sb, source, fnode):
    """return <expr> -> return null (functional)."""
    lo, hi = _fn_range(fnode)
    root = parse(source).root_node
    out, i = [], 0
    for n in _walk(root):
        if n.type == "return_statement" and lo <= _line(n) <= hi:
            val = n.children[1] if len(n.children) > 1 and n.children[1].is_named else None
            if val is None or _text(sb, val) in ("null", "undefined"):
                continue
            out.append((f"return[{i}]->null", val.start_byte, val.end_byte, b"null", _line(val)))
            i += 1
    return out


def _behavioral_sites(parse, sb, source, fnode):
    """Swap each arithmetic/comparison/logical operator (behavioral)."""
    lo, hi = _fn_range(fnode)
    root = parse(source).root_node
    out, i = [], 0
    for n in _walk(root):
        if n.type == "binary_expression" and lo <= _line(n) <= hi:
            op = n.child_by_field_name("operator")
            tok = _text(sb, op) if op else None
            if tok in _SWAP:
                out.append((f"op[{i}]", op.start_byte, op.end_byte, _SWAP[tok].encode(), _line(op)))
                i += 1
    return out


def _observable_sites(parse, sb, source, fnode):
    """Nullify a bare logger emit (observable)."""
    lo, hi = _fn_range(fnode)
    root = parse(source).root_node
    out, i = [], 0
    for n in _walk(root):
        if n.type != "expression_statement" or not (lo <= _line(n) <= hi):
            continue
        call = n.children[0]
        if call.type != "call_expression":
            continue
        fn = call.child_by_field_name("function")
        if not fn or fn.type != "member_expression":
            continue
        recv = fn.child_by_field_name("object")
        meth = fn.child_by_field_name("property")
        args = call.child_by_field_name("arguments")
        rname = _text(sb, recv).split(".")[-1].lstrip("_").lower() if recv else ""
        if rname not in _LOGGER_NAMES or not meth or _text(sb, meth) not in _EMIT_METHODS:
            continue
        if any(a.type in ("call_expression", "await_expression") for a in _walk(args)):
            continue  # impure args — nullify would drop a side effect (false proven)
        out.append((f"emit[{i}]->void", call.start_byte, call.end_byte, b"void 0", _line(call)))
        i += 1
    return out


# Non-Error sentinel synthesized once per mutant (resilient spike): non-Error so it
# escapes toThrow(Error); .message=a[0] so message-pins survive; args kept verbatim.
_SENTINEL_DECL = b"\nclass __SmSentinel { constructor(...a) { this.message = a[0]; } }\n"


def _resilient_sites(parse, sb, source, branch: ErrorBranch):
    """Resilient operators by branch kind (the JS/TS operator set, resilient spike):
    a ``throw`` -> throw-type-swap to a sentinel; a ``catch`` -> recovery-neutralize
    (perturb the recovered value, blank-catch fallback). Both throw (sync and async
    ``rejects.toThrow``) and catch-recovery conform cross-language.

    The spike's THIRD candidate, instanceof-routing (swap a catch-body
    ``instanceof`` type), is **deliberately NOT implemented — and the reason is
    structural, not a missing fixture.** Python's resilient level has no
    error-type-routing operator at all: ``mutate.make_mutants`` gives an ``except``
    branch only const-perturb + ``blank-except``; the sole type-swap
    (``_swap_raise_type``) is raise-side. So routing in Python is pinned only
    indirectly via the raise sentinel, and the ``except``/``catch`` verdict comes
    from blank-except/blank-catch. An instanceof-routing operator's only
    value-adding cases are exactly where it would make JS-resilient STRICTER than
    Python (a test that pins a recovery value but not which type routes to it: JS=gap,
    Python=proven) — which would break the cross-language semantic identity that is
    P7's success criterion. Adding it is a rubric-level decision (a deliberate
    JS-stricter stance, like bare ``toThrow()``), not a slice-time port. Deferred
    with that reason; see docs/spikes/P7-resilient-spike.md."""
    root = parse(source).root_node
    if branch.kind == "throw":
        return _throw_swap_sites(sb, root, branch)
    if branch.kind == "except":  # a `catch` clause
        return _catch_recovery_sites(sb, root, branch)
    return []


def _throw_swap_sites(sb, root, branch):
    """throw new <Type>(<single string>) -> throw new __SmSentinel(...). Scoped to a
    recognizable single-stringish-arg throw (else no-signal — the multi-arg trap)."""
    out = []
    for n in _walk(root):
        if n.type != "throw_statement" or _line(n) != branch.lineno:
            continue
        ne = next((c for c in _walk(n) if c.type == "new_expression"), None)
        if ne is None:
            continue
        ctor = ne.child_by_field_name("constructor")
        args = ne.child_by_field_name("arguments")
        named = [c for c in args.children if c.is_named] if args else []
        if not ctor or len(named) != 1 or named[0].type not in ("string", "template_string"):
            continue  # not new <Type>(<one string>) -> no-signal
        mutated = (sb[:ctor.start_byte] + b"__SmSentinel" + sb[ctor.end_byte:] + _SENTINEL_DECL)
        out.append(("throw-type-swap", 0, len(sb), mutated, branch.lineno))
    return out


def _perturb_literal(sb, lit) -> bytes | None:
    """Value-preserving-shape perturbation of a non-string literal (Python `_perturb`
    analog). Strings are NOT perturbed — asserting an error message is brittle and
    would manufacture a false gap (mirrors `mutate._significant_consts`)."""
    t = sb[lit.start_byte:lit.end_byte]
    return {"number": b"(" + t + b" + 1)", "true": b"false", "false": b"true",
            "null": b"0"}.get(lit.type)


def _catch_recovery_sites(sb, root, branch):
    """Is the catch's RECOVERY pinned? Perturb each non-string literal in the catch
    body (the `blank-except` analog); if none, blank the body so a recovery-value
    test dies. A test that only triggers the catch (not asserting its result)
    survives — the gap signal."""
    catch = next((n for n in _walk(root)
                  if n.type == "catch_clause" and _line(n) == branch.lineno), None)
    if catch is None:
        return []
    body = catch.child_by_field_name("body")
    if body is None:
        return []
    lits = [n for n in _walk(body) if n.type in ("number", "true", "false", "null")]
    out = []
    for i, lit in enumerate(lits):
        rep = _perturb_literal(sb, lit)
        if rep is not None:
            out.append((f"recovery-const[{i}]", lit.start_byte, lit.end_byte, rep, branch.lineno))
    if not out:  # no perturbable constant -> blank the recovery body
        out.append(("blank-catch", body.start_byte, body.end_byte, b"{}", branch.lineno))
    return out


# --- injected vitest setup + config ------------------------------------------

_SETUP_JS = """
import { beforeEach, afterEach } from "vitest";
import { appendFileSync } from "node:fs";
const LOG = process.env.SM_ATTRIB_LOG;
function counts() {
  const c = globalThis.__VITEST_COVERAGE__ || {}, out = {};
  for (const [f, d] of Object.entries(c)) for (const [k, v] of Object.entries((d && d.s) || {})) out[k] = v;
  return out;
}
let before;
beforeEach(() => { before = counts(); });
afterEach((ctx) => {
  const after = counts(), touched = [];
  for (const [k, v] of Object.entries(after)) if (v > (before[k] ?? 0)) touched.push(k);
  appendFileSync(LOG, JSON.stringify({ file: ctx.task.file?.name, name: ctx.task.name, s: touched }) + "\\n");
});
"""


# Target vitest/vite config filenames, in vitest's own resolution priority. The
# coverage() injected config INHERITS the first one found (environment / setupFiles /
# plugins / jsx) instead of replacing it.
_CONFIG_NAMES = (
    "vitest.config.ts", "vitest.config.mts", "vitest.config.cts",
    "vitest.config.js", "vitest.config.mjs", "vitest.config.cjs",
    "vite.config.ts", "vite.config.mts", "vite.config.cts",
    "vite.config.js", "vite.config.mjs", "vite.config.cjs",
)


def _find_target_config(cwd: str) -> str | None:
    """The target project's vitest/vite config filename (relative to cwd), or None."""
    for name in _CONFIG_NAMES:
        if (Path(cwd) / name).exists():
            return name
    return None


def _config_js(setup_name: str, module_path: str, covdir: Path, target_config: str | None = None) -> str:
    test_block = (
        f"  setupFiles: [{json.dumps('./' + setup_name)}],\n"
        '  coverage: { provider: "istanbul", reporter: ["json"], all: false,\n'
        f"    include: [{json.dumps(module_path)}], reportsDirectory: {json.dumps(str(covdir))} }},\n"
    )
    if target_config is None:
        # No target config: standalone block (byte-identical to the pre-merge config —
        # this is the path the JS/TS conformance suite exercises and guards).
        return (
            'import { defineConfig } from "vitest/config";\n'
            "export default defineConfig({ test: {\n"
            + test_block
            + "} });\n"
        )
    # A target config exists: INHERIT it. vitest's `--config` REPLACES rather than
    # merges, so without this a .tsx project's `environment: jsdom` + `setupFiles`
    # (and `.ts`/`.js` projects' own setup) would be dropped — component tests then
    # error at collection (P7-tsx-jsx-spike.md, build slice 1). We merge our
    # attribution setup + coverage onto the target's RESOLVED config (a default
    # export that is a config object, or a sync/async config function). FAIL LOUD: if
    # the import or merge fails, vitest errors and coverage() raises — we never
    # silently fall back to standalone, which would re-drop the environment invisibly.
    return (
        'import { defineConfig, mergeConfig } from "vitest/config";\n'
        f"import _smTarget from {json.dumps('./' + target_config)};\n"
        'const _smEnv = { command: "serve", mode: "test", isSsrBuild: false, isPreview: false };\n'
        'const _smBase = typeof _smTarget === "function" ? await _smTarget(_smEnv) : _smTarget;\n'
        "export default mergeConfig(_smBase, defineConfig({ test: {\n"
        + test_block
        + "} }));\n"
    )
