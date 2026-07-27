"""Behavioral equivalent-mutant control (tests-only; never shipped).

Both nodes are the SAME suspicious operator — ``x * 1`` — which looks like an
equivalent mutant under the ``* ↔ /`` swap. It is not: ``6 * 1`` is ``int 6`` but
``6 / 1`` is ``float 6.0``. Whether the swap is a gap depends entirely on the
test, which is exactly why behavioral cannot exclude it:

- scale_loose: a value-only test (``== 6``) — ``6.0 == 6`` is True, so the
               ``*1→/1`` mutant survives → ``behavioral: gap-unasserted`` (the
               honest lower bound — the type is unpinned).
- scale_strict: a type-pinning test — ``6.0`` is not an ``int``, so the mutant
                dies → ``behavioral: proven``.

The same mutant is gap-unasserted under one test and proven under another, so it
is killable, not equivalent. Excluding it (to look symmetric with resilient's
message-string exclusion) would hide the type gap — a false ``proven``.
"""


def scale_loose(x):
    return x * 1  # value-only test leaves *1→/1 unkilled (6 == 6.0)


def scale_strict(x):
    return x * 1  # type-pinning test kills *1→/1 (int 6 vs float 6.0)
