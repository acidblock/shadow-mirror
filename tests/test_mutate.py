"""Fast unit tests for the observable emit operator's detection gates.

Pure AST — no coverage/pytest subprocess — so these run in the fast tier and
pin the three conservatisms in ``mutate._is_emit`` directly.
"""

import textwrap

from shadow_mirror.mutate import make_observable_mutants, observable_site_lines
from shadow_mirror.tree import build_functions


def _fn(tmp_path, src, leaf):
    path = tmp_path / "m.py"
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    fns = {f.qualname.split(".")[-1]: f for f in build_functions(path)}
    return path.read_text(encoding="utf-8"), fns[leaf]


def test_detects_logger_emits_name_and_attribute_receivers(tmp_path):
    src, fn = _fn(tmp_path, """
        import logging
        logger = logging.getLogger("x")
        class C:
            def f(self, a):
                logger.info("got %s", a)       # Name receiver 'logger'
                self._logger.warning(a)        # Attribute receiver '_logger'
                return a
    """, "f")
    assert len(make_observable_mutants(src, fn)) == 2
    assert len(observable_site_lines(src, fn)) == 2


def test_skips_domain_method_named_like_a_log_level(tmp_path):
    # Receiver-name guard: a domain sink named log/error is NOT an emit, so it
    # is never nullified — a domain side effect can't be mislabeled `proven`.
    src, fn = _fn(tmp_path, """
        def f(self, a):
            self.audit.log(a)
            self.db.error(a)
            return a
    """, "f")
    assert make_observable_mutants(src, fn) == []
    assert observable_site_lines(src, fn) == set()


def test_skips_emit_with_side_effecting_argument(tmp_path):
    # Purity gate: nullifying would also drop compute(a)'s side effect.
    src, fn = _fn(tmp_path, """
        import logging
        logger = logging.getLogger("x")
        def f(a):
            logger.info("got %s", compute(a))
            return a
    """, "f")
    assert make_observable_mutants(src, fn) == []
    assert observable_site_lines(src, fn) == set()
