"""Validation rules."""
import pytest

from arbor.pipeline.validate import (
    LEAF_FANOUT_MAX,
    LEAF_FANOUT_MIN,
    ValidationFailure,
    truncate_high_fanout,
    validate_tree,
)


VALID_TREE = {
    "root": "T",
    "branches": [{
        "label": "A",
        "children": [
            {"label": f"leaf {i}"} for i in range(5)
        ],
    }],
}


def test_valid_tree_passes():
    validate_tree(VALID_TREE, layers=3)


def test_missing_root_fails():
    bad = {"branches": []}
    with pytest.raises(ValidationFailure, match="root"):
        validate_tree(bad, layers=2)


def test_too_deep_fails():
    too_deep = {
        "root": "T",
        "branches": [{"label": "A", "children": [
            {"label": "B", "children": [
                {"label": "C", "children": [
                    {"label": "leaf"},
                ]},
            ]},
        ]}],
    }
    with pytest.raises(ValidationFailure, match="depth"):
        validate_tree(too_deep, layers=2)


def test_low_leaf_fanout_fails():
    low = {
        "root": "T",
        "branches": [{
            "label": "A",
            "children": [{"label": "leaf 1"}, {"label": "leaf 2"}],
        }],
    }
    with pytest.raises(ValidationFailure, match="leaf_fanout_low"):
        validate_tree(low, layers=3)


def test_high_leaf_fanout_fails():
    high = {
        "root": "T",
        "branches": [{
            "label": "A",
            "children": [{"label": f"leaf {i}"} for i in range(8)],
        }],
    }
    with pytest.raises(ValidationFailure, match="leaf_fanout_high"):
        validate_tree(high, layers=3)


def test_truncate_high_fanout_clips_to_max():
    high = {
        "root": "T",
        "branches": [{
            "label": "A",
            "children": [{"label": f"leaf {i}"} for i in range(10)],
        }],
    }
    fixed = truncate_high_fanout(high)
    assert len(fixed["branches"][0]["children"]) == LEAF_FANOUT_MAX
