"""JsAdapter — the JavaScript :class:`LanguageAdapter` (P7): tree-sitter + Istanbul + vitest.

A thin grammar binding over :class:`shadow_mirror.adapters._treesitter._TreeSitterAdapter`
(the shared, grammar-agnostic implementation). NOT imported by ``adapters/__init__``
(that would pull ``tree_sitter`` into the base env and break the Python map path on
machines without it — C1). Import it explicitly:
``from shadow_mirror.adapters.javascript import JsAdapter``. Needs the ``[js]`` extra
(tree-sitter + tree-sitter-javascript) and, in the target project, ``npx``/vitest.

The companion :class:`shadow_mirror.adapters.typescript.TsAdapter` binds the same
base to the TypeScript grammar — JS and TS differ only by parser (TS is a grammar
superset; see ``docs/spikes/P7-typescript-spike.md``).
"""

from __future__ import annotations

import tree_sitter_javascript as tsjs

from ._treesitter import _TreeSitterAdapter

__all__ = ["JsAdapter"]


class JsAdapter(_TreeSitterAdapter):
    """Implements :class:`shadow_mirror.spi.LanguageAdapter` for JavaScript."""

    def __init__(self):
        super().__init__("javascript", tsjs.language())
