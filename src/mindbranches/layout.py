"""Pure-Python geometry for the MindBranches diagram.

Recursive horizontal fan: every level fans rightward from its parent.
Each subtree gets a vertical extent equal to the sum of its descendants.
Within that extent, the parent pill sits vertically centered against its
children, and bezier connectors fan from parent-right to each child-left.

Tree shape: every node is ``{label, children?}``. Leaves have no children.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .depth import is_leaf, tree_depth

THEMES: dict[str, dict] = {
    "cream": {
        "bg": "#FBF7F0",
        "ink": "#1A1A1A",
        "muted": "#5A5A5A",
        "accents": [
            "#3F4B5B",
            "#B5644F",
            "#7A8B6B",
            "#5C7A92",
            "#9A6F86",
            "#B89254",
        ],
    },
    "dark": {
        "bg": "#161616",
        "ink": "#F0EBE3",
        "muted": "#9A9A9A",
        "accents": [
            "#7A8DA3",
            "#D08574",
            "#9DAE8C",
            "#85A0B8",
            "#B695A8",
            "#D2B17D",
        ],
    },
    "mono": {
        "bg": "#FBF7F0",
        "ink": "#1A1A1A",
        "muted": "#5A5A5A",
        "accents": ["#1A1A1A"],
    },
}

# One column per layer. Index 1 = root, 2 = first ring, etc.
# Non-leaf columns hold short pill labels. The leaf column gets extra width
# because leaves carry full ideas (sentences), not bullet fragments.
COLUMN_WIDTHS: dict[int, int] = {1: 320, 2: 260, 3: 240, 4: 230, 5: 220}
LEAF_COLUMN_WIDTH = 340

PILL_FONT_BY_DEPTH = {1: 30, 2: 20, 3: 17, 4: 15, 5: 14}
PILL_PAD_Y_BY_DEPTH = {1: 18, 2: 12, 3: 10, 4: 9, 5: 8}
PILL_PAD_X_BY_DEPTH = {1: 22, 2: 18, 3: 14, 4: 12, 5: 11}

LEAF_FONT_SIZE = 14
LEAF_LINE_HEIGHT = 1.55
LEAF_BLOCK_PAD = 8  # extra vertical breathing room for leaf blocks

PADDING = 80
INTER_COLUMN_GAP = 90
INTER_SUBTREE_GAP = 24  # between sibling subtrees vertically


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: str = "transparent"
    stroke: str = "transparent"
    stroke_width: float = 0
    radius: float = 12


@dataclass
class TextLine:
    text: str
    x: float
    y: float
    font_size: int
    weight: int = 400
    color: str = "#1A1A1A"
    anchor: str = "start"
    line_height: float = 1.2


@dataclass
class BezierPath:
    d: str
    stroke: str
    width: float = 2


@dataclass
class Layout:
    width: int
    height: int
    bg: str
    ink: str
    rects: list[Rect] = field(default_factory=list)
    texts: list[TextLine] = field(default_factory=list)
    paths: list[BezierPath] = field(default_factory=list)


# ------------------------- text helpers -------------------------

def _approx_text_width(text: str, font_size: int, weight: int = 400) -> float:
    factor = 0.55 if weight < 500 else (0.58 if weight < 700 else 0.60)
    return len(text) * font_size * factor


def _wrap_text(text: str, max_width: float, font_size: int, weight: int = 400) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if _approx_text_width(candidate, font_size, weight) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [text]


def _column_width(depth: int, total_layers: int | None = None) -> int:
    """Width of the column at this depth.

    The leaf column (depth == total_layers) gets extra width so substantive
    leaf text reads as paragraphs, not as cramped wrapped fragments.
    """
    if total_layers is not None and depth == total_layers:
        return LEAF_COLUMN_WIDTH
    return COLUMN_WIDTHS.get(depth, COLUMN_WIDTHS[5])


def _pill_metrics(
    node: dict[str, Any], depth: int, total_layers: int | None = None
) -> tuple[list[str], int, int]:
    col = _column_width(depth, total_layers)
    font = PILL_FONT_BY_DEPTH.get(depth, PILL_FONT_BY_DEPTH[5])
    pad_x = PILL_PAD_X_BY_DEPTH.get(depth, PILL_PAD_X_BY_DEPTH[5])
    pad_y = PILL_PAD_Y_BY_DEPTH.get(depth, PILL_PAD_Y_BY_DEPTH[5])
    weight = 700 if depth == 1 else 500
    lines = _wrap_text(node.get("label", ""), col - 2 * pad_x, font, weight=weight)
    pill_h = len(lines) * font * 1.2 + 2 * pad_y
    return lines, font, pill_h


def _leaf_metrics(
    node: dict[str, Any], depth: int, total_layers: int | None = None
) -> tuple[list[str], int]:
    """Return the wrapped lines and total block height for a leaf at this depth."""
    col = _column_width(depth, total_layers)
    lines = _wrap_text(node.get("label", ""), col, LEAF_FONT_SIZE)
    h = int(len(lines) * LEAF_FONT_SIZE * LEAF_LINE_HEIGHT) + LEAF_BLOCK_PAD
    return lines, h


# ------------------------- measurement -------------------------

def _measure(node: dict[str, Any], depth: int, total_layers: int) -> int:
    """Return the vertical height this subtree wants."""
    if is_leaf(node) or depth == total_layers:
        _, h = _leaf_metrics(node, depth, total_layers)
        return h

    _, _, pill_h = _pill_metrics(node, depth, total_layers)
    children = node.get("children", []) or []
    if not children:
        return pill_h
    children_total = sum(_measure(c, depth + 1, total_layers) for c in children)
    children_total += INTER_SUBTREE_GAP * max(0, len(children) - 1)
    return max(pill_h, children_total)


# ------------------------- emission -------------------------

def _emit(
    layout: Layout,
    node: dict[str, Any],
    depth: int,
    total_layers: int,
    x: float,
    y_top: float,
    allocated_h: float,
    accent: str,
    palette: dict,
) -> tuple[float, float, float]:
    """Place a subtree starting at (x, y_top) with vertical space allocated_h.

    Returns (anchor_left_x, anchor_mid_y, anchor_right_x) -- the points the
    parent's bezier should aim for and that the children's beziers come from.
    """
    col = _column_width(depth, total_layers)

    # Leaf: render as plain text, vertically centered within the allocation.
    if is_leaf(node) or depth == total_layers:
        lines, _ = _leaf_metrics(node, depth, total_layers)
        block_h = len(lines) * LEAF_FONT_SIZE * LEAF_LINE_HEIGHT
        cursor = y_top + (allocated_h - block_h) / 2
        for line in lines:
            layout.texts.append(
                TextLine(
                    text=line,
                    x=x,
                    y=cursor,
                    font_size=LEAF_FONT_SIZE,
                    weight=400,
                    color=palette["ink"],
                    line_height=LEAF_LINE_HEIGHT,
                )
            )
            cursor += LEAF_FONT_SIZE * LEAF_LINE_HEIGHT
        # Anchor on the left edge of the text block, vertically centered.
        return x, y_top + allocated_h / 2, x + col

    # Non-leaf: pill at this column, centered vertically inside allocation.
    pill_lines, pill_font, pill_h = _pill_metrics(node, depth, total_layers)
    pad_x = PILL_PAD_X_BY_DEPTH.get(depth, PILL_PAD_X_BY_DEPTH[5])
    pad_y = PILL_PAD_Y_BY_DEPTH.get(depth, PILL_PAD_Y_BY_DEPTH[5])
    pill_y = y_top + (allocated_h - pill_h) / 2

    if depth == 1:
        # Root: filled dark
        layout.rects.append(
            Rect(x=x, y=pill_y, w=col, h=pill_h, fill=palette["ink"], radius=14)
        )
        label_color = palette["bg"]
        text_anchor = "middle"
    elif depth == 2:
        # Top-level branches: filled accent
        layout.rects.append(
            Rect(x=x, y=pill_y, w=col, h=pill_h, fill=accent, radius=10)
        )
        label_color = palette["bg"]
        text_anchor = "start"
    else:
        # Deeper non-leaf: outline-only pill
        layout.rects.append(
            Rect(
                x=x, y=pill_y, w=col, h=pill_h,
                fill="transparent", stroke=accent, stroke_width=1, radius=8,
            )
        )
        label_color = accent
        text_anchor = "start"

    # Pill label
    label_y = pill_y + pad_y
    if text_anchor == "middle":
        label_x = x + col / 2
    else:
        label_x = x + pad_x
    for line in pill_lines:
        layout.texts.append(
            TextLine(
                text=line,
                x=label_x,
                y=label_y,
                font_size=pill_font,
                weight=700 if depth == 1 else 500,
                color=label_color,
                anchor=text_anchor,
                line_height=1.2,
            )
        )
        label_y += pill_font * 1.2

    # Place children to the right, centered vertically against this pill.
    children = node.get("children", []) or []
    if not children:
        return x, pill_y + pill_h / 2, x + col

    child_heights = [_measure(c, depth + 1, total_layers) for c in children]
    children_total = sum(child_heights) + INTER_SUBTREE_GAP * max(0, len(children) - 1)
    children_top = y_top + (allocated_h - children_total) / 2

    parent_right_x = x + col
    parent_mid_y = pill_y + pill_h / 2

    cursor = children_top
    for c, ch in zip(children, child_heights):
        child_x = x + col + INTER_COLUMN_GAP
        child_left_x, child_mid_y, _ = _emit(
            layout, c, depth + 1, total_layers,
            child_x, cursor, ch, accent, palette,
        )
        # Bezier connector
        gap = child_left_x - parent_right_x
        c1x = parent_right_x + gap / 2
        c2x = parent_right_x + gap / 2
        d = (
            f"M {parent_right_x:.1f} {parent_mid_y:.1f} "
            f"C {c1x:.1f} {parent_mid_y:.1f}, "
            f"{c2x:.1f} {child_mid_y:.1f}, "
            f"{child_left_x:.1f} {child_mid_y:.1f}"
        )
        layout.paths.append(BezierPath(d=d, stroke=accent, width=2))

        cursor += ch + INTER_SUBTREE_GAP

    return x, parent_mid_y, parent_right_x


# ------------------------- top-level -------------------------

def compute_layout(tree: dict[str, Any], width: int = 1600, theme: str = "cream") -> Layout:
    palette = THEMES.get(theme, THEMES["cream"])
    accents = palette["accents"]

    layers_decl = tree.get("layers")
    measured = tree_depth(tree.get("branches", [])) if tree.get("branches") else 1
    total_layers = max(2, layers_decl or measured)

    branches = tree.get("branches", []) or []

    # Canvas width is determined by the deepest branch -- sum column widths +
    # gaps + padding. Width param is treated as a minimum.
    cols_used = list(range(1, total_layers + 1))
    canvas_w = (
        sum(_column_width(d, total_layers) for d in cols_used)
        + INTER_COLUMN_GAP * (len(cols_used) - 1)
        + 2 * PADDING
    )
    canvas_w = max(canvas_w, width)

    if not branches:
        # Just the root.
        _, _, pill_h = _pill_metrics({"label": tree.get("root", "")}, depth=1)
        h = int(pill_h + 2 * PADDING)
        layout = Layout(width=canvas_w, height=h, bg=palette["bg"], ink=palette["ink"])
        _emit(
            layout, {"label": tree.get("root", "")}, 1, total_layers,
            PADDING, PADDING, pill_h, accents[0], palette,
        )
        return layout

    # Treat the root as a node whose children are the top-level branches.
    # Measure the per-branch heights directly (each gets its own accent color
    # for downstream descendants).
    branch_heights = [_measure(b, 2, total_layers) for b in branches]
    branches_total = sum(branch_heights) + INTER_SUBTREE_GAP * max(0, len(branches) - 1)

    _, _, root_pill_h = _pill_metrics({"label": tree.get("root", "")}, depth=1)
    content_h = max(branches_total, root_pill_h)
    canvas_h = int(content_h + 2 * PADDING)

    layout = Layout(width=canvas_w, height=canvas_h, bg=palette["bg"], ink=palette["ink"])

    # Place root pill (filled dark) at column 1, centered vertically.
    root_lines, root_font, _ = _pill_metrics({"label": tree.get("root", "")}, depth=1)
    root_w = COLUMN_WIDTHS[1]
    root_pad_y = PILL_PAD_Y_BY_DEPTH[1]
    root_y = PADDING + (content_h - root_pill_h) / 2
    layout.rects.append(
        Rect(x=PADDING, y=root_y, w=root_w, h=root_pill_h, fill=palette["ink"], radius=14)
    )
    label_y = root_y + root_pad_y
    cx = PADDING + root_w / 2
    for line in root_lines:
        layout.texts.append(
            TextLine(
                text=line,
                x=cx,
                y=label_y,
                font_size=root_font,
                weight=700,
                color=palette["bg"],
                anchor="middle",
                line_height=1.2,
            )
        )
        label_y += root_font * 1.2

    # Place each top-level branch in column 2, with its own accent.
    branches_top = PADDING + (content_h - branches_total) / 2
    cursor = branches_top
    branch_x = PADDING + root_w + INTER_COLUMN_GAP
    root_right_x = PADDING + root_w
    root_mid_y = root_y + root_pill_h / 2

    for i, (branch, h) in enumerate(zip(branches, branch_heights)):
        accent = accents[i % len(accents)]
        child_left_x, child_mid_y, _ = _emit(
            layout, branch, 2, total_layers,
            branch_x, cursor, h, accent, palette,
        )
        # Bezier from root edge to branch
        gap = child_left_x - root_right_x
        c1x = root_right_x + gap / 2
        c2x = root_right_x + gap / 2
        d = (
            f"M {root_right_x:.1f} {root_mid_y:.1f} "
            f"C {c1x:.1f} {root_mid_y:.1f}, "
            f"{c2x:.1f} {child_mid_y:.1f}, "
            f"{child_left_x:.1f} {child_mid_y:.1f}"
        )
        layout.paths.append(BezierPath(d=d, stroke=accent, width=2))
        cursor += h + INTER_SUBTREE_GAP

    return layout
