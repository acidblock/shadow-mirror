"""Tests for the operation-tree extractor and node-identity scheme (R1)."""

from shadow_mirror.tree import build_tree

FIXTURE = "tests/fixtures/resilient_demo/orders.py"


def test_extracts_both_raises_and_excepts():
    kinds = [b.kind for b in build_tree(FIXTURE).branches]
    assert kinds.count("except") == 2  # normalize_qty, apply_discount
    assert kinds.count("raise") == 4  # charge, charge_async, refund, validate_sku


def test_node_id_is_path_qualname_kind_ordinal():
    by_q = {b.qualname: b for b in build_tree(FIXTURE).branches}
    assert by_q["charge"].node_id.endswith("::charge#raise:0")
    assert by_q["apply_discount"].node_id.endswith("::apply_discount#except:0")
    assert by_q["charge"].exc_type == "ValueError"
    assert by_q["refund"].exc_type == "LookupError"


def test_shape_hash_present_and_deterministic():
    first = build_tree(FIXTURE).branches
    second = build_tree(FIXTURE).branches
    assert all(b.shape_hash for b in first)
    assert [b.shape_hash for b in first] == [b.shape_hash for b in second]


def test_ordinal_increments_within_a_function(tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text(
        "def f(x):\n"
        "    if x:\n"
        "        raise ValueError('a')\n"
        "    raise TypeError('b')\n"
    )
    ordinals = sorted(
        b.node_id.rsplit(":", 1)[-1] for b in build_tree(str(mod)).branches if b.kind == "raise"
    )
    assert ordinals == ["0", "1"]
