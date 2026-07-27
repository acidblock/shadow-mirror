"""Language adapters implementing :class:`shadow_mirror.spi.LanguageAdapter`."""

import importlib

from .python import PythonAdapter

__all__ = ["PythonAdapter", "adapter_for"]

# language name (and common aliases) -> (module, class, extra) for lazy loading.
_LOADERS = {
    "javascript": (".javascript", "JsAdapter", "js"),
    "js": (".javascript", "JsAdapter", "js"),
    "typescript": (".typescript", "TsAdapter", "ts"),
    "ts": (".typescript", "TsAdapter", "ts"),
    "tsx": (".tsx", "TsxAdapter", "ts"),
    "jsx": (".tsx", "TsxAdapter", "ts"),
}


def adapter_for(language: str):
    """Return the :class:`~shadow_mirror.spi.LanguageAdapter` for ``language``.

    ``"python"`` returns the always-available :class:`PythonAdapter`. The tree-sitter
    (JS/TS/TSX) adapters are imported **lazily** so the base env and C1 never require
    ``tree-sitter`` unless a caller actually asks for one — and a missing ``[js]`` /
    ``[ts]`` extra surfaces a clear error instead of an opaque ImportError. Accepts
    ``js`` / ``ts`` / ``jsx`` aliases."""
    lang = (language or "python").lower()
    if lang == "python":
        return PythonAdapter()
    if lang not in _LOADERS:
        raise ValueError(
            f"unknown language {language!r} (expected python|javascript|typescript|tsx)"
        )
    mod, cls, extra = _LOADERS[lang]
    try:
        module = importlib.import_module(mod, __package__)
    except ImportError as exc:  # the [js]/[ts] extra (tree-sitter) is not installed
        raise RuntimeError(f"language {lang!r} needs the [{extra}] extra (tree-sitter)") from exc
    return getattr(module, cls)()
