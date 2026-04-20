"""Pure-Python geometry for the MindBranches diagram."""

from __future__ import annotations

from dataclasses import dataclass, field

THEMES: dict[str, dict] = {
    "cream": {
        "bg": "#FBF7F0",
        "ink": "#1A1A1A",
        "muted": "#5A5A5A",
        "accents": [
            "#3F4B5B",  # slate
            "#B5644F",  # terracotta
            "#7A8B6B",  # sage
            "#5C7A92",  # dusty blue
            "#9A6F86",  # mauve
            "#B89254",  # mustard
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

ROOT_FONT_SIZE = 30
BRANCH_FONT_SIZE = 20
BULLET_FONT_SIZE = 15
ROOT_LINE_HEIGHT = 1.2
BRANCH_LINE_HEIGHT = 1.2
BULLET_LINE_HEIGHT = 1.55

PADDING = 80
ROOT_WIDTH = 320
ROOT_PADDING_X = 22
ROOT_PADDING_Y = 18
BRANCH_PADDING_X = 18
BRANCH_PADDING_Y = 10
BULLET_INDENT = 16
PILL_TO_BULLET_GAP = 10
INTER_BRANCH_GAP = 28
ROOT_TO_BRANCH_GAP = 220


@dataclass
class TextLine:
    text: str
    x: float
    y: float
    font_size: int
    weight: int = 400
    color: str = "#1A1A1A"


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: str = "transparent"
    stroke: str = "transparent"
    radius: float = 12


@dataclass
class BranchVisual:
    pill: Rect
    label: TextLine
    bullets: list[TextLine] = field(default_factory=list)
    bezier: str = ""
    accent: str = "#1A1A1A"


@dataclass
class Layout:
    width: int
    height: int
    bg: str
    ink: str
    root_rect: Rect
    root_label: TextLine
    branches: list[BranchVisual]


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


def compute_layout(tree: dict, width: int = 1600, theme: str = "cream") -> Layout:
    palette = THEMES.get(theme, THEMES["cream"])
    accents = palette["accents"]

    root_text = tree["root"]
    root_lines = _wrap_text(
        root_text, ROOT_WIDTH - 2 * ROOT_PADDING_X, ROOT_FONT_SIZE, weight=700
    )
    root_text_height = len(root_lines) * ROOT_FONT_SIZE * ROOT_LINE_HEIGHT
    root_rect_h = root_text_height + 2 * ROOT_PADDING_Y

    branch_zone_x = PADDING + ROOT_WIDTH + ROOT_TO_BRANCH_GAP
    pill_w = width - branch_zone_x - PADDING
    bullet_indent_x = branch_zone_x + BULLET_INDENT
    bullet_max_width = width - bullet_indent_x - PADDING

    branch_specs: list[dict] = []
    for b in tree["branches"]:
        label_lines = _wrap_text(
            b["label"],
            pill_w - 2 * BRANCH_PADDING_X,
            BRANCH_FONT_SIZE,
            weight=500,
        )
        label_height = len(label_lines) * BRANCH_FONT_SIZE * BRANCH_LINE_HEIGHT
        pill_h = label_height + 2 * BRANCH_PADDING_Y

        bullet_blocks: list[list[str]] = []
        for c in b["children"]:
            cl = _wrap_text(c, bullet_max_width, BULLET_FONT_SIZE)
            bullet_blocks.append(cl)
        total_bullet_height = sum(
            len(bl) * BULLET_FONT_SIZE * BULLET_LINE_HEIGHT for bl in bullet_blocks
        )

        branch_total_h = pill_h + PILL_TO_BULLET_GAP + total_bullet_height
        branch_specs.append(
            {
                "label_lines": label_lines,
                "pill_h": pill_h,
                "bullet_blocks": bullet_blocks,
                "branch_h": branch_total_h,
            }
        )

    n = len(branch_specs)
    total_branch_height = (
        sum(s["branch_h"] for s in branch_specs) + INTER_BRANCH_GAP * max(0, n - 1)
    )
    content_height = max(root_rect_h, total_branch_height)
    height = int(content_height + 2 * PADDING)

    root_y = (height - root_rect_h) / 2
    root_rect = Rect(
        x=PADDING,
        y=root_y,
        w=ROOT_WIDTH,
        h=root_rect_h,
        fill=palette["ink"],
        stroke=palette["ink"],
        radius=14,
    )
    root_label = TextLine(
        text="\n".join(root_lines),
        x=PADDING + ROOT_WIDTH / 2,
        y=root_y + ROOT_PADDING_Y,
        font_size=ROOT_FONT_SIZE,
        weight=700,
        color=palette["bg"],
    )

    branches_top = (height - total_branch_height) / 2
    cursor_y = branches_top
    branch_visuals: list[BranchVisual] = []
    root_right_x = PADDING + ROOT_WIDTH
    root_right_y = root_y + root_rect_h / 2

    for i, spec in enumerate(branch_specs):
        accent = accents[i % len(accents)]
        pill = Rect(
            x=branch_zone_x,
            y=cursor_y,
            w=pill_w,
            h=spec["pill_h"],
            fill=accent,
            stroke=accent,
            radius=10,
        )
        label = TextLine(
            text="\n".join(spec["label_lines"]),
            x=branch_zone_x + BRANCH_PADDING_X,
            y=cursor_y + BRANCH_PADDING_Y,
            font_size=BRANCH_FONT_SIZE,
            weight=500,
            color=palette["bg"],
        )

        bullets: list[TextLine] = []
        bullet_y = cursor_y + spec["pill_h"] + PILL_TO_BULLET_GAP
        for block in spec["bullet_blocks"]:
            for line in block:
                bullets.append(
                    TextLine(
                        text=line,
                        x=bullet_indent_x,
                        y=bullet_y,
                        font_size=BULLET_FONT_SIZE,
                        weight=400,
                        color=palette["ink"],
                    )
                )
                bullet_y += BULLET_FONT_SIZE * BULLET_LINE_HEIGHT

        pill_mid_y = cursor_y + spec["pill_h"] / 2
        gap = branch_zone_x - root_right_x
        c1x = root_right_x + gap / 2
        c1y = root_right_y
        c2x = root_right_x + gap / 2
        c2y = pill_mid_y
        bezier = (
            f"M {root_right_x:.1f} {root_right_y:.1f} "
            f"C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f}, "
            f"{branch_zone_x:.1f} {pill_mid_y:.1f}"
        )

        branch_visuals.append(
            BranchVisual(
                pill=pill,
                label=label,
                bullets=bullets,
                bezier=bezier,
                accent=accent,
            )
        )
        cursor_y += spec["branch_h"] + INTER_BRANCH_GAP

    return Layout(
        width=width,
        height=height,
        bg=palette["bg"],
        ink=palette["ink"],
        root_rect=root_rect,
        root_label=root_label,
        branches=branch_visuals,
    )
