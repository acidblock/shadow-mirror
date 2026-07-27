"""TsAdapter — the TypeScript :class:`LanguageAdapter` (P7): tree-sitter + Istanbul + vitest.

A thin grammar binding over :class:`shadow_mirror.adapters._treesitter._TreeSitterAdapter`,
identical to :class:`shadow_mirror.adapters.javascript.JsAdapter` except for the
grammar. TypeScript is a documented grammar *superset* of JavaScript — the
function / throw / catch / binary-expression nodes and their fields are identically
named, and the extra type-annotation nodes are simply never matched by the
site-finders. The one seam that could have broken this — Istanbul reporting coverage
against transpiled positions rather than original ``.ts`` lines — was spiked and
cleared (vitest's esbuild transform + ``@vitest/coverage-istanbul`` report
original-source positions): ``docs/spikes/P7-typescript-spike.md``.

NOT imported by ``adapters/__init__`` (C1). Import explicitly:
``from shadow_mirror.adapters.typescript import TsAdapter``. Needs the ``[ts]`` extra
(tree-sitter + tree-sitter-typescript) and, in the target project, ``npx``/vitest.

``.tsx``/JSX uses a distinct grammar (``language_tsx``) and is spiked separately
(``docs/spikes/P7-tsx-jsx-spike.md``): the grammar + coverage seam port cleanly.
Both build slices of that spike are **done**: slice 1 — ``coverage()`` *inherits* a
target project's vitest config (``environment``/``setupFiles``/``esbuild`` jsx) via
``mergeConfig`` instead of replacing it (see ``_treesitter._config_js``); slice 2 —
the ``.tsx`` grammar binding itself, :class:`shadow_mirror.adapters.tsx.TsxAdapter`
(``language_tsx``), with a Preact component-render conformance fixture.
"""

from __future__ import annotations

import tree_sitter_typescript as tsts

from ._treesitter import _TreeSitterAdapter

__all__ = ["TsAdapter"]


class TsAdapter(_TreeSitterAdapter):
    """Implements :class:`shadow_mirror.spi.LanguageAdapter` for TypeScript."""

    def __init__(self):
        super().__init__("typescript", tsts.language_typescript())
