"""Tree-depth helpers shared by extract, layout, server, and CLI.

The tree is uniformly recursive: every node is ``{label, children?}``.
Leaves have no ``children`` (or an empty list). The total number of layers
counts the root as layer 1 and the deepest leaf level as layer ``N``.

Examples for layers = N:
- N = 2: root + leaf branches (one ring of labels under the root)
- N = 3: root + section nodes + leaf children (the original Arbor shape)
- N = 4: root + section + subsection + leaf
- N = 5: root + part + section + subsection + leaf
"""

from __future__ import annotations

from typing import Any

MIN_LAYERS = 2
MAX_LAYERS = 5


def suggest_layers(byte_count: int) -> int:
    """Heuristic depth suggestion based on input size in bytes (~1 byte/char)."""
    if byte_count < 1500:
        return 2
    if byte_count < 8000:
        return 3
    if byte_count < 50000:
        return 4
    return 5


def clamp_layers(n: int | None, fallback: int) -> int:
    if n is None:
        return fallback
    return max(MIN_LAYERS, min(MAX_LAYERS, int(n)))


def is_leaf(node: dict[str, Any]) -> bool:
    children = node.get("children")
    return not children


def iter_leaves(node: dict[str, Any]):
    if is_leaf(node):
        yield node
        return
    for child in node["children"]:
        yield from iter_leaves(child)


def normalize_tree(tree: dict[str, Any]) -> dict[str, Any]:
    """Coerce a tree to the uniform shape: every node is {label, children}.

    Tolerates legacy trees where ``children`` items are bare strings.
    """

    def norm_node(node: Any) -> dict[str, Any]:
        if isinstance(node, str):
            return {"label": node, "children": []}
        if isinstance(node, dict):
            label = str(node.get("label", "")).strip()
            kids = node.get("children", []) or []
            return {"label": label, "children": [norm_node(k) for k in kids]}
        return {"label": str(node), "children": []}

    return {
        "root": str(tree.get("root", "")).strip(),
        "layers": tree.get("layers"),
        "branches": [norm_node(b) for b in tree.get("branches", []) or []],
    }


def tree_depth(branches: list[dict[str, Any]]) -> int:
    """Return the deepest layer index reached by any path from root.

    Layer 1 is the root, so a non-empty `branches` list always contributes
    layer 2 minimum.
    """
    if not branches:
        return 1

    def node_depth(node: dict[str, Any]) -> int:
        if is_leaf(node):
            return 1
        return 1 + max(node_depth(c) for c in node["children"])

    return 1 + max(node_depth(b) for b in branches)
