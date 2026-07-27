"""TsxAdapter — the TypeScript-with-JSX (.tsx) :class:`LanguageAdapter` (P7).

A thin grammar binding over the shared
:class:`shadow_mirror.adapters._treesitter._TreeSitterAdapter`, identical to
:class:`shadow_mirror.adapters.typescript.TsAdapter` except it binds the **tsx**
grammar (``tree_sitter_typescript.language_tsx``). JSX is parsed by the same
site-finders — the ``jsx_*`` nodes it adds are never matched, so they are ignored,
while JSX-embedded logic (``{n * 2}``) and ``return <jsx>`` are real operator sites
(see ``docs/spikes/P7-tsx-jsx-spike.md``).

Render-style ``.tsx`` is unblocked by build slice 1 (``coverage()`` inherits the
target project's vitest config — ``environment``/``setupFiles``/``esbuild`` jsx —
rather than replacing it).

**Kept SEPARATE from typescript.py on purpose.** tree-sitter ships two grammars
because the tsx grammar reads ``<T>`` as the start of a JSX element, so TypeScript's
``<T>expr`` type-cast syntax mis-parses under ``language_tsx``. ``.ts`` casts need
``language_typescript`` (TsAdapter); ``.tsx`` needs ``language_tsx`` (here). Do NOT
"simplify" by merging the two — it would silently break ``.ts`` cast parsing.

NOT imported by ``adapters/__init__`` (C1). Import explicitly:
``from shadow_mirror.adapters.tsx import TsxAdapter``. Needs the ``[ts]`` extra
(``tree-sitter-typescript`` ships both grammars) and, in the target project,
``npx``/vitest with a DOM ``environment`` (e.g. happy-dom) for component renders.
"""

from __future__ import annotations

import tree_sitter_typescript as tsts

from ._treesitter import _TreeSitterAdapter

__all__ = ["TsxAdapter"]


class TsxAdapter(_TreeSitterAdapter):
    """Implements :class:`shadow_mirror.spi.LanguageAdapter` for TypeScript + JSX."""

    def __init__(self):
        super().__init__("tsx", tsts.language_tsx())
