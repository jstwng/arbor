"""Schema + leaf-fanout validation."""
from __future__ import annotations

from typing import Any

LEAF_FANOUT_MIN = 5
LEAF_FANOUT_MAX = 6
MAX_RETRIES = 1


class ValidationFailure(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _is_leaf(node: dict) -> bool:
    return not node.get("children")


def _depth(node: dict) -> int:
    if _is_leaf(node):
        return 1
    return 1 + max(_depth(c) for c in node["children"])


def _walk_leaf_parents(node: dict):
    """Yield nodes whose every child is a leaf."""
    children = node.get("children") or []
    if children and all(_is_leaf(c) for c in children):
        yield node
    for c in children:
        yield from _walk_leaf_parents(c)


def validate_tree(tree: dict[str, Any], layers: int) -> None:
    if "root" not in tree or not isinstance(tree["root"], str):
        raise ValidationFailure("schema", "missing or non-string `root`")
    if "branches" not in tree or not isinstance(tree["branches"], list):
        raise ValidationFailure("schema", "missing or non-list `branches`")

    pseudo_root = {"label": tree["root"], "children": tree["branches"]}
    actual_depth = _depth(pseudo_root)
    if actual_depth > layers:
        raise ValidationFailure(
            "depth", f"tree depth {actual_depth} > requested layers {layers}"
        )

    for parent in _walk_leaf_parents(pseudo_root):
        n = len(parent["children"])
        if n < LEAF_FANOUT_MIN:
            raise ValidationFailure(
                "leaf_fanout_low",
                f"parent {parent.get('label')!r} has {n} leaves; need >= {LEAF_FANOUT_MIN}",
            )
        if n > LEAF_FANOUT_MAX:
            raise ValidationFailure(
                "leaf_fanout_high",
                f"parent {parent.get('label')!r} has {n} leaves; need <= {LEAF_FANOUT_MAX}",
            )


def truncate_high_fanout(tree: dict[str, Any]) -> dict[str, Any]:
    """Clip any leaf-parent's children to LEAF_FANOUT_MAX. Mutates and returns."""
    pseudo_root = {"label": tree["root"], "children": tree["branches"]}
    for parent in _walk_leaf_parents(pseudo_root):
        if len(parent["children"]) > LEAF_FANOUT_MAX:
            parent["children"] = parent["children"][:LEAF_FANOUT_MAX]
    return tree
