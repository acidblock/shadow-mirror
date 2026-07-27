"""Mutation operators scoped to a single error branch (the resilient signal).

"Asserted" is operationalized as: mutate the branch; if some test fails, a
test pins this branch's behavior. Operators are **value-perturbing**, not mere
deletion — deletion of a recovery body crashes the function and any test that
reaches it, which would collapse the signal back to "executed ≈ proven" (i.e.
back to coverage.py). Perturbation instead distinguishes a test that *pins the
branch's outcome* (the recovered value, or the raised type) from one that
merely *triggers* it.
"""

from __future__ import annotations

import ast
import copy

from .tree import ErrorBranch, FunctionNode

__all__ = ["make_mutants", "make_functional_mutants", "make_behavioral_mutants",
           "behavioral_site_lines", "make_observable_mutants", "observable_site_lines"]

# Behavioral operator-swap tables (the reference operator set S, frozen in
# docs/coverage-levels.md). Swaps flip the meaning so a test that pins the
# logic dies; surviving mutants are a *lower bound* (may include equivalents).
_BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
          ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult, ast.Pow: ast.Mult}
_CMP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt,
        ast.Gt: ast.LtE, ast.LtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
        ast.In: ast.NotIn, ast.NotIn: ast.In}
_BOOLOP = {ast.And: ast.Or, ast.Or: ast.And}

# A sentinel raised type that no normal ``pytest.raises(X)`` matches: it is a
# BaseException subclass (so ``except Exception`` / ``raises(Exception)`` miss it)
# and — unlike KeyboardInterrupt/SystemExit — not specially handled by pytest.
# Swapping *any* raised type to it kills a test that pins the type, without a
# lookup table that would silently ignore custom/out-of-table exceptions.
_SENTINEL = "GeneratorExit"

_NO = object()


def _perturb(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return value + "_MUT" if value else "MUT"
    if value is None:
        return 0
    return _NO


def _find(module_ast: ast.Module, branch: ErrorBranch) -> ast.AST | None:
    want = ast.Raise if branch.kind == "raise" else ast.ExceptHandler
    for node in ast.walk(module_ast):
        if isinstance(node, want) and node.lineno == branch.lineno:
            return node
    return None


def _significant_consts(node: ast.AST) -> list[ast.Constant]:
    """Constants worth perturbing — excludes string literals.

    A string in a ``raise``/``except`` is almost always the human-readable
    *message* (``raise ValueError("amount must be positive")``), not behavior a
    test should be required to assert. Perturbing it produces an **equivalent
    mutant**: it survives any reasonable suite, so under all-must-die aggregation
    it would manufacture a false ``gap-unasserted`` ("assert your error text").
    Excluding strings keeps the resilient signal an honest lower bound — it may
    miss a genuinely significant string (an error code), but never demands a
    message assertion. Non-string constants (status codes, thresholds, sentinels)
    stay in: ``raise HttpError(503, "down")`` keeps the ``503`` mutant, drops the
    ``"down"`` mutant.
    """
    return [
        c for c in ast.walk(node)
        if isinstance(c, ast.Constant) and not isinstance(c.value, str)
    ]


def _already_sentinel(exc: ast.expr) -> bool:
    target = exc.func if isinstance(exc, ast.Call) else exc
    return isinstance(target, ast.Name) and target.id == _SENTINEL


def _swap_raise_type(raise_node: ast.Raise) -> bool:
    """Swap the raised type to the sentinel. Works for any named exception."""
    exc = raise_node.exc
    if exc is None or _already_sentinel(exc):
        return False  # bare ``raise`` / already the sentinel
    sentinel = ast.Name(id=_SENTINEL, ctx=ast.Load())
    if isinstance(exc, ast.Call):  # raise Err(args...) -> raise GeneratorExit(args...)
        exc.func = sentinel
        return True
    if isinstance(exc, (ast.Name, ast.Attribute)):  # raise Err -> raise GeneratorExit
        raise_node.exc = sentinel
        return True
    return False


def make_mutants(source: str, branch: ErrorBranch) -> list[tuple[str, str]]:
    """Return ``[(label, mutated_source), ...]`` for ``branch`` (may be empty)."""
    base = ast.parse(source)
    if _find(base, branch) is None:
        return []

    out: list[tuple[str, str]] = []

    if branch.kind == "raise":
        clone = copy.deepcopy(base)
        node = _find(clone, branch)
        if isinstance(node, ast.Raise) and _swap_raise_type(node):
            out.append(("raise-type-swap", ast.unparse(ast.fix_missing_locations(clone))))

    n_consts = len(_significant_consts(_find(base, branch)))
    for i in range(n_consts):
        clone = copy.deepcopy(base)
        const = _significant_consts(_find(clone, branch))[i]
        new_value = _perturb(const.value)
        if new_value is not _NO and new_value != const.value:
            const.value = new_value
            out.append((f"const[{i}]→{new_value!r}", ast.unparse(clone)))

    if not out and branch.kind == "except":
        clone = copy.deepcopy(base)
        node = _find(clone, branch)
        node.body = [ast.Pass()]  # type: ignore[attr-defined]
        out.append(("blank-except", ast.unparse(ast.fix_missing_locations(clone))))

    return out


# --- function-scoped mutation (functional + behavioral) -----------------

_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _owned(fn: ast.AST):
    """Nodes inside ``fn``'s body, not descending into nested scopes."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _NESTED):
            stack.extend(ast.iter_child_nodes(node))


def _find_func(module: ast.Module, fnode: FunctionNode) -> ast.AST | None:
    leaf = fnode.qualname.split(".")[-1]
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == leaf and node.lineno == fnode.lineno
        ):
            return node
    return None


def _returns(fn: ast.AST) -> list[ast.Return]:
    return [
        n for n in _owned(fn)
        if isinstance(n, ast.Return)
        and n.value is not None
        and not (isinstance(n.value, ast.Constant) and n.value.value is None)
    ]


def make_functional_mutants(source: str, fnode: FunctionNode) -> list[tuple[str, str, int]]:
    """Replace each ``return <value>`` with ``return None`` — is the output checked?

    Returns ``(label, mutated_source, lineno)`` per site, so the caller can gate
    and aggregate each return **independently** (per-site worst-first)."""
    base = ast.parse(source)
    fn = _find_func(base, fnode)
    if fn is None:
        return []
    out: list[tuple[str, str, int]] = []
    for i, site in enumerate(_returns(fn)):
        clone = copy.deepcopy(base)
        target = _returns(_find_func(clone, fnode))[i]
        target.value = ast.Constant(value=None)
        out.append((f"return[{i}]→None", ast.unparse(ast.fix_missing_locations(clone)), site.lineno))
    return out


def _swap_sites(fn: ast.AST) -> list[tuple[ast.AST, int | None]]:
    """Deterministic list of swappable operator sites (node, compare-index)."""
    sites: list[tuple[ast.AST, int | None]] = []
    for node in _owned(fn):
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
            sites.append((node, None))
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOLOP:
            sites.append((node, None))
        elif isinstance(node, ast.Compare):
            for j, op in enumerate(node.ops):
                if type(op) in _CMP:
                    sites.append((node, j))
    return sites


def make_behavioral_mutants(source: str, fnode: FunctionNode) -> list[tuple[str, str, int]]:
    """Swap each arithmetic/comparison/boolean operator — is the logic pinned?

    Returns ``(label, mutated_source, lineno)`` per swap site, for per-site
    gating and worst-first aggregation."""
    base = ast.parse(source)
    fn = _find_func(base, fnode)
    if fn is None:
        return []
    out: list[tuple[str, str, int]] = []
    for k, (site, _sj) in enumerate(_swap_sites(fn)):
        clone = copy.deepcopy(base)
        node, j = _swap_sites(_find_func(clone, fnode))[k]
        if j is None and isinstance(node, ast.BinOp):
            node.op = _BINOP[type(node.op)]()
        elif j is None and isinstance(node, ast.BoolOp):
            node.op = _BOOLOP[type(node.op)]()
        elif isinstance(node, ast.Compare):
            node.ops[j] = _CMP[type(node.ops[j])]()
        out.append((f"op[{k}]", ast.unparse(ast.fix_missing_locations(clone)), site.lineno))
    return out


def behavioral_site_lines(source: str, fnode: FunctionNode) -> set[int]:
    """Source lines carrying a behavioral swap site — the lines that must run
    for ``make_behavioral_mutants`` to be falsifiable (the gate's target set)."""
    base = ast.parse(source)
    fn = _find_func(base, fnode)
    if fn is None:
        return set()
    return {node.lineno for node, _j in _swap_sites(fn)}


# --- observable: is an emitted signal (log / metric / event) asserted? -----

# Logging-style emit methods. A metrics/event/trace backend (statsd.incr,
# tracer.start_span, a custom emit()) would extend this set via config; stdlib
# ``logging`` is the universally-detectable surface, so rubric v2 scopes to it.
_EMIT_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)
# Receiver names that read as a logger. A *heuristic* (not a type check): it
# scopes the method-name match to logger-shaped receivers so a domain method
# named ``log``/``error``/``warning`` (``audit.log(x)``, ``db.error(x)``) is not
# mistaken for an emit. Underscore-prefixed and upper-case spellings count
# (``self._logger``, ``LOG``); unconventionally-named loggers are missed — the
# safe (lower-bound) direction. Precise receiver-type detection is a v2.x item.
_LOGGER_NAMES = frozenset({"log", "logger", "logging"})


def _is_emit(node: ast.AST) -> bool:
    """A bare logging-style emit statement with side-effect-free arguments.

    Three gates, each a deliberate conservatism toward a lower bound:

    1. ``ast.Expr`` only — the call's return value must be unused, so nullifying
       it is data-flow-preserving.
    2. ``<logger>.<method>(...)`` — the method name is in :data:`_EMIT_METHODS`
       **and** the receiver name is logger-shaped (:data:`_LOGGER_NAMES`). The
       receiver guard stops a domain method named like a log level from being
       nullified (which would mislabel a domain side effect as an observability
       assertion — a false ``proven``).
    3. Pure arguments — no nested ``Call``/``Await``. Nullifying
       ``logger.info("x", f())`` would also drop ``f()``'s side effect, so a
       non-observability test could die — again a false ``proven``.
    """
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
        return False
    call = node.value
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in _EMIT_METHODS):
        return False
    receiver = call.func.value
    rname = getattr(receiver, "id", None) or getattr(receiver, "attr", "") or ""
    if rname.lstrip("_").lower() not in _LOGGER_NAMES:
        return False
    args = [*call.args, *(k.value for k in call.keywords)]
    return not any(isinstance(s, (ast.Call, ast.Await)) for a in args for s in ast.walk(a))


def _emit_exprs(fn: ast.AST) -> list[ast.Expr]:
    return [n for n in _owned(fn) if _is_emit(n)]


def observable_site_lines(source: str, fnode: FunctionNode) -> set[int]:
    """Lines carrying a nullifiable emit — the observable level's target set."""
    base = ast.parse(source)
    fn = _find_func(base, fnode)
    return {e.lineno for e in _emit_exprs(fn)} if fn else set()


def make_observable_mutants(source: str, fnode: FunctionNode) -> list[tuple[str, str, int]]:
    """Nullify each bare emit (``logger.info(...)`` → ``None``) — is it observed?

    An emit's return value is unused, so the nullification is
    data-flow-preserving: the only test that can die is one that asserts on the
    emitted signal (e.g. via pytest ``caplog``). The cleanest mutation signal —
    no equivalent-mutant ambiguity, since deleting an emit is never behaviorally
    equivalent to a test that checks it."""
    base = ast.parse(source)
    fn = _find_func(base, fnode)
    if fn is None:
        return []
    out: list[tuple[str, str, int]] = []
    for i, site in enumerate(_emit_exprs(fn)):
        clone = copy.deepcopy(base)
        target = _emit_exprs(_find_func(clone, fnode))[i]
        target.value = ast.Constant(value=None)
        out.append((f"emit[{i}]→None", ast.unparse(ast.fix_missing_locations(clone)), site.lineno))
    return out
