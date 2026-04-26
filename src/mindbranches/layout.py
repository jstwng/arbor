"""Pure-Python geometry for the MindBranches diagram.

Tree shape: every node is ``{label, children?}``. Leaves have no children.
Layout strategy:
- Root sits at center-left, anchored vertically to the middle of the canvas.
- Top-level branches stack vertically on the right, each connected to the
  root by a bezier.
- Inside each top-level branch, sub-content stacks vertically and is
  indented with each depth step. Non-leaf descendants render as smaller
  pills; the deepest layer renders as plain text.
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

# Typography per depth (depth 1 = root, depth 2 = top-level branches, ...).
ROOT_FONT_SIZE = 30
PILL_FONT_BY_DEPTH = {2: 20, 3: 16, 4: 14, 5: 13}
PILL_PAD_Y_BY_DEPTH = {2: 10, 3: 8, 4: 7, 5: 6}
PILL_PAD_X_BY_DEPTH = {2: 18, 3: 14, 4: 12, 5: 10}
LEAF_FONT_SIZE = 15
LEAF_LINE_HEIGHT = 1.55

PADDING = 80
ROOT_WIDTH = 320
ROOT_PAD_X = 22
ROOT_PAD_Y = 18
ROOT_TO_BRANCH_GAP = 220
INTER_BRANCH_GAP = 32
PILL_TO_CHILDREN_GAP = 10
INTER_CHILD_GAP = 8
INDENT_PER_DEPTH = 22


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


def _measure_subtree(
    node: dict[str, Any],
    depth: int,
    available_w: float,
) -> float:
    """Return the total height a node + its descendants will occupy."""
    if is_leaf(node):
        lines = _wrap_text(node["label"], available_w, LEAF_FONT_SIZE)
        return len(lines) * LEAF_FONT_SIZE * LEAF_LINE_HEIGHT

    pill_font = PILL_FONT_BY_DEPTH.get(depth, PILL_FONT_BY_DEPTH[5])
    pill_pad_y = PILL_PAD_Y_BY_DEPTH.get(depth, PILL_PAD_Y_BY_DEPTH[5])
    pill_pad_x = PILL_PAD_X_BY_DEPTH.get(depth, PILL_PAD_X_BY_DEPTH[5])
    pill_inner_w = available_w - 2 * pill_pad_x
    pill_lines = _wrap_text(node["label"], pill_inner_w, pill_font, weight=500)
    pill_h = len(pill_lines) * pill_font * 1.2 + 2 * pill_pad_y

    indent = INDENT_PER_DEPTH
    child_w = available_w - indent
    children = node.get("children", [])
    if not children:
        return pill_h
    children_h = sum(_measure_subtree(c, depth + 1, child_w) for c in children)
    children_h += INTER_CHILD_GAP * max(0, len(children) - 1)
    return pill_h + PILL_TO_CHILDREN_GAP + children_h


def _emit_subtree(
    layout: Layout,
    node: dict[str, Any],
    depth: int,
    x: float,
    y: float,
    available_w: float,
    accent: str,
    palette: dict,
) -> float:
    """Place a node + descendants starting at (x, y). Return consumed height."""
    if is_leaf(node):
        lines = _wrap_text(node["label"], available_w, LEAF_FONT_SIZE)
        cursor = y
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
        return cursor - y

    pill_font = PILL_FONT_BY_DEPTH.get(depth, PILL_FONT_BY_DEPTH[5])
    pill_pad_y = PILL_PAD_Y_BY_DEPTH.get(depth, PILL_PAD_Y_BY_DEPTH[5])
    pill_pad_x = PILL_PAD_X_BY_DEPTH.get(depth, PILL_PAD_X_BY_DEPTH[5])
    pill_inner_w = available_w - 2 * pill_pad_x
    pill_lines = _wrap_text(node["label"], pill_inner_w, pill_font, weight=500)
    pill_h = len(pill_lines) * pill_font * 1.2 + 2 * pill_pad_y

    # Top-level branches (depth 2) get the solid accent fill; deeper non-leaf
    # pills get an outline-only treatment so the hierarchy reads at a glance.
    if depth == 2:
        layout.rects.append(
            Rect(
                x=x, y=y, w=available_w, h=pill_h,
                fill=accent, stroke=accent, radius=10,
            )
        )
        label_color = palette["bg"]
    else:
        layout.rects.append(
            Rect(
                x=x, y=y, w=available_w, h=pill_h,
                fill="transparent", stroke=accent, stroke_width=1, radius=8,
            )
        )
        label_color = accent

    # Pill label (left-aligned inside the pill, supports wrapping)
    label_y = y + pill_pad_y
    for line in pill_lines:
        layout.texts.append(
            TextLine(
                text=line,
                x=x + pill_pad_x,
                y=label_y,
                font_size=pill_font,
                weight=500,
                color=label_color,
                line_height=1.2,
            )
        )
        label_y += pill_font * 1.2

    # Children stacked below, indented
    indent = INDENT_PER_DEPTH
    child_x = x + indent
    child_w = available_w - indent
    cursor = y + pill_h + PILL_TO_CHILDREN_GAP
    children = node.get("children", [])
    for i, child in enumerate(children):
        used = _emit_subtree(layout, child, depth + 1, child_x, cursor, child_w, accent, palette)
        cursor += used
        if i < len(children) - 1:
            cursor += INTER_CHILD_GAP

    return cursor - y


def compute_layout(tree: dict[str, Any], width: int = 1600, theme: str = "cream") -> Layout:
    palette = THEMES.get(theme, THEMES["cream"])
    accents = palette["accents"]
    bg = palette["bg"]
    ink = palette["ink"]

    branches = tree.get("branches", [])
    if not branches:
        # Degenerate: just the root.
        h = ROOT_PAD_Y * 2 + ROOT_FONT_SIZE * 1.2 + PADDING * 2
        return Layout(width=width, height=int(h), bg=bg, ink=ink)

    # Root geometry
    root_lines = _wrap_text(
        tree.get("root", ""), ROOT_WIDTH - 2 * ROOT_PAD_X, ROOT_FONT_SIZE, weight=700
    )
    root_text_h = len(root_lines) * ROOT_FONT_SIZE * 1.2
    root_h = root_text_h + 2 * ROOT_PAD_Y

    branch_x = PADDING + ROOT_WIDTH + ROOT_TO_BRANCH_GAP
    branch_w = width - branch_x - PADDING

    # Measure each top-level branch first so we can size + center the canvas.
    branch_heights = [
        _measure_subtree(b, depth=2, available_w=branch_w) for b in branches
    ]
    total_branch_h = sum(branch_heights) + INTER_BRANCH_GAP * max(0, len(branches) - 1)
    content_h = max(root_h, total_branch_h)
    canvas_h = int(content_h + 2 * PADDING)

    layout = Layout(width=width, height=canvas_h, bg=bg, ink=ink)

    # Root rect + label (ink fill, bg-color text)
    root_y = (canvas_h - root_h) / 2
    layout.rects.append(
        Rect(
            x=PADDING, y=root_y, w=ROOT_WIDTH, h=root_h,
            fill=ink, stroke=ink, radius=14,
        )
    )
    # Root label centered
    n = len(root_lines)
    total_text_h = n * ROOT_FONT_SIZE * 1.2
    start_y = root_y + (root_h - total_text_h) / 2
    cx = PADDING + ROOT_WIDTH / 2
    cursor_y = start_y
    for line in root_lines:
        layout.texts.append(
            TextLine(
                text=line,
                x=cx,
                y=cursor_y,
                font_size=ROOT_FONT_SIZE,
                weight=700,
                color=bg,
                anchor="middle",
                line_height=1.2,
            )
        )
        cursor_y += ROOT_FONT_SIZE * 1.2

    # Top-level branches: centered as a stack against the root
    branches_top = (canvas_h - total_branch_h) / 2
    cursor_y = branches_top
    root_right_edge = (PADDING + ROOT_WIDTH, root_y + root_h / 2)

    for i, (branch, h) in enumerate(zip(branches, branch_heights)):
        accent = accents[i % len(accents)]

        # Bezier from root edge to this branch's top pill (or first leaf)
        # We anchor to the vertical mid of the FIRST node's pill / leaf.
        pill_font = PILL_FONT_BY_DEPTH.get(2, 20)
        pill_pad_y = PILL_PAD_Y_BY_DEPTH.get(2, 10)
        pill_pad_x = PILL_PAD_X_BY_DEPTH.get(2, 18)
        if is_leaf(branch):
            anchor_h = LEAF_FONT_SIZE * LEAF_LINE_HEIGHT
        else:
            pill_lines = _wrap_text(
                branch["label"],
                branch_w - 2 * pill_pad_x,
                pill_font,
                weight=500,
            )
            anchor_h = len(pill_lines) * pill_font * 1.2 + 2 * pill_pad_y
        anchor_mid_y = cursor_y + anchor_h / 2

        rx, ry = root_right_edge
        gap = branch_x - rx
        c1x = rx + gap / 2
        c2x = rx + gap / 2
        d = (
            f"M {rx:.1f} {ry:.1f} "
            f"C {c1x:.1f} {ry:.1f}, {c2x:.1f} {anchor_mid_y:.1f}, "
            f"{branch_x:.1f} {anchor_mid_y:.1f}"
        )
        layout.paths.append(BezierPath(d=d, stroke=accent, width=2))

        _emit_subtree(layout, branch, depth=2, x=branch_x, y=cursor_y, available_w=branch_w, accent=accent, palette=palette)
        cursor_y += h + INTER_BRANCH_GAP

    return layout


# Backwards-compatible attribute names a few callers used to peek at:
def make_layout(*args, **kwargs):  # pragma: no cover
    return compute_layout(*args, **kwargs)
