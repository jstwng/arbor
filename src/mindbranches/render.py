"""Render Layout to SVG, HTML, and PNG."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .layout import Layout, Rect, TextLine

PKG_ROOT = Path(__file__).parent
TEMPLATE_DIR = PKG_ROOT / "templates"
FONTS_DIR = PKG_ROOT / "fonts"


def _font_face_css() -> str:
    weights = {"Regular": 400, "Medium": 500, "Bold": 700}
    rules: list[str] = []
    for name, weight in weights.items():
        path = FONTS_DIR / f"Inter-{name}.ttf"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            "@font-face { "
            "font-family: 'Inter'; font-style: normal; "
            f"font-weight: {weight}; "
            f"src: url(data:font/ttf;base64,{b64}) format('truetype'); "
            "}"
        )
    return "\n".join(rules)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _multi_line_text(
    text_line: TextLine,
    line_height_em: float,
    text_anchor: str = "start",
) -> str:
    lines = text_line.text.split("\n")
    first_baseline = text_line.y + text_line.font_size * 0.95
    parts = [
        f'<text x="{text_line.x:.1f}" y="{first_baseline:.1f}" '
        f'font-size="{text_line.font_size}" font-weight="{text_line.weight}" '
        f'fill="{text_line.color}" font-family="Inter, sans-serif" '
        f'text-anchor="{text_anchor}">'
    ]
    for i, line in enumerate(lines):
        dy = "0" if i == 0 else f"{text_line.font_size * line_height_em:.1f}"
        parts.append(f'<tspan x="{text_line.x:.1f}" dy="{dy}">{_escape(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def _render_root_text(text_line: TextLine, rect: Rect) -> str:
    lines = text_line.text.split("\n")
    line_height_em = 1.2
    n = len(lines)
    total_h = n * text_line.font_size * line_height_em
    start_y = rect.y + (rect.h - total_h) / 2 + text_line.font_size * 0.85
    cx = rect.x + rect.w / 2
    parts = [
        f'<text x="{cx:.1f}" y="{start_y:.1f}" '
        f'font-size="{text_line.font_size}" font-weight="{text_line.weight}" '
        f'fill="{text_line.color}" font-family="Inter, sans-serif" '
        f'text-anchor="middle">'
    ]
    for i, line in enumerate(lines):
        dy = "0" if i == 0 else f"{text_line.font_size * line_height_em:.1f}"
        parts.append(f'<tspan x="{cx:.1f}" dy="{dy}">{_escape(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def render_svg(layout: Layout) -> str:
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {layout.width} {layout.height}" '
        f'width="{layout.width}" height="{layout.height}">'
    )
    parts.append(f"<style>{_font_face_css()}</style>")
    parts.append(
        f'<rect x="0" y="0" width="{layout.width}" height="{layout.height}" '
        f'fill="{layout.bg}"/>'
    )

    for b in layout.branches:
        parts.append(
            f'<path d="{b.bezier}" stroke="{b.accent}" stroke-width="2" '
            f'fill="none" stroke-linecap="round"/>'
        )

    r = layout.root_rect
    parts.append(
        f'<rect x="{r.x:.1f}" y="{r.y:.1f}" width="{r.w:.1f}" height="{r.h:.1f}" '
        f'rx="{r.radius}" ry="{r.radius}" fill="{r.fill}"/>'
    )
    parts.append(_render_root_text(layout.root_label, r))

    for b in layout.branches:
        p = b.pill
        parts.append(
            f'<rect x="{p.x:.1f}" y="{p.y:.1f}" width="{p.w:.1f}" height="{p.h:.1f}" '
            f'rx="{p.radius}" ry="{p.radius}" fill="{p.fill}"/>'
        )
        parts.append(_multi_line_text(b.label, line_height_em=1.2))
        for bullet in b.bullets:
            parts.append(_multi_line_text(bullet, line_height_em=1.55))

    parts.append("</svg>")
    return "\n".join(parts)


def render_html(svg: str, bg: str = "#FBF7F0") -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
    )
    template = env.get_template("diagram.html.j2")
    return template.render(svg=svg, bg=bg)


def render_png_via_playwright(
    html_path: Path,
    out_path: Path,
    viewport_width: int,
    viewport_height: int,
) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=2,
        )
        page.goto(html_path.absolute().as_uri())
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(out_path), full_page=True, omit_background=False)
        browser.close()


def write_outputs(tree: dict, layout: Layout, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = render_svg(layout)
    html = render_html(svg, bg=layout.bg)

    paths = {
        "tree.json": out_dir / "tree.json",
        "output.svg": out_dir / "output.svg",
        "output.html": out_dir / "output.html",
        "output.png": out_dir / "output.png",
    }
    paths["tree.json"].write_text(json.dumps(tree, indent=2))
    paths["output.svg"].write_text(svg)
    paths["output.html"].write_text(html)
    render_png_via_playwright(
        paths["output.html"],
        paths["output.png"],
        viewport_width=layout.width,
        viewport_height=layout.height,
    )
    return paths
