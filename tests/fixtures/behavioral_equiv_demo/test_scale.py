"""One node pinned loosely (value only), one pinned strictly (value + type)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import scale  # noqa: E402


def test_scale_loose_value_only():
    assert scale.scale_loose(6) == 6  # 6.0 == 6 → the *1→/1 mutant survives


def test_scale_strict_pins_type():
    result = scale.scale_strict(6)
    assert result == 6 and isinstance(result, int)  # float 6.0 → the mutant dies
