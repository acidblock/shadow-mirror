"""Within-branch resilient control (tests-only; never shipped).

Both raises are pinned by TYPE only (``pytest.raises(T)``). The difference is
what *else* the raise carries:

- http_guard: ``raise HttpError(503, "down")`` — the 503 is a SIGNIFICANT,
              unasserted constant. Old any-killed read `proven` (the type-swap
              died); all-must-die reads `gap-unasserted` (the 503 mutant
              survives — nobody asserts the status).
- require   : ``raise ValueError("x is required")`` — only a message string.
              Strings are not mutated, so the only mutant is the type-swap,
              which dies → `proven`. The negative control: an unasserted message
              must NOT manufacture a gap.
"""


class HttpError(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def http_guard(status):
    if status >= 400:
        raise HttpError(503, "down")  # 503 significant + unasserted
    return status


def require(x):
    if not x:
        raise ValueError("x is required")  # message-only
    return x


def lookup(table, key):
    try:
        return table[key]
    except KeyError:
        return "default"  # string-only recovery — exercises the blank-except path
