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


def _text_svg(t: TextLine) -> str:
    baseline = t.y + t.font_size * 0.95
    return (
        f'<text x="{t.x:.1f}" y="{baseline:.1f}" '
        f'font-size="{t.font_size}" font-weight="{t.weight}" '
        f'fill="{t.color}" font-family="Inter, sans-serif" '
        f'text-anchor="{t.anchor}">{_escape(t.text)}</text>'
    )


def _rect_svg(r: Rect) -> str:
    stroke_attr = (
        f' stroke="{r.stroke}" stroke-width="{r.stroke_width}"'
        if r.stroke != "transparent" and r.stroke_width > 0
        else ""
    )
    return (
        f'<rect x="{r.x:.1f}" y="{r.y:.1f}" width="{r.w:.1f}" height="{r.h:.1f}" '
        f'rx="{r.radius}" ry="{r.radius}" fill="{r.fill}"{stroke_attr}/>'
    )


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

    # Bezier paths first (under everything else)
    for p in layout.paths:
        parts.append(
            f'<path d="{p.d}" stroke="{p.stroke}" stroke-width="{p.width}" '
            f'fill="none" stroke-linecap="round"/>'
        )

    # Then rects (root + pills)
    for r in layout.rects:
        parts.append(_rect_svg(r))

    # Then text on top
    for t in layout.texts:
        parts.append(_text_svg(t))

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
            device_scale_factor=3,
        )
        page.goto(html_path.absolute().as_uri())
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(out_path), full_page=True, omit_background=False)
        browser.close()


def render_live_skeleton(width: int, height: int, bg: str, job_id: str) -> str:
    """Return a self-contained HTML page that DOM-patches its SVG via postMessage.

    The parent page (app.js) forwards ``branch_partial`` and ``tree_complete``
    SSE events to this iframe via ``postMessage``.  No direct EventSource
    connection is opened here, which avoids the single-reader-per-queue
    constraint on the server-side SSE stream.
    """
    font_css = _font_face_css()
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
{font_css}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 100%; height: 100%; background: {bg}; overflow: hidden; }}
svg {{ display: block; width: 100%; height: 100%; }}
.arbor-anim {{ opacity: 0; transition: opacity 250ms ease; }}
.arbor-anim.shown {{ opacity: 1; }}
</style>
</head>
<body>
<svg id="live-svg"
     xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {width} {height}"
     width="{width}"
     height="{height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="{bg}"/>
</svg>
<script>
(function () {{
  var svg = document.getElementById("live-svg");
  var NS = "http://www.w3.org/2000/svg";
  var known = {{}};

  function applySnapshot(snap) {{
    if (snap.viewBox) svg.setAttribute("viewBox", snap.viewBox);
    if (snap.width)   svg.setAttribute("width",   snap.width);
    if (snap.height)  svg.setAttribute("height",  snap.height);
    var els = snap.elements || [];
    els.forEach(function(el) {{
      if (known[el.id]) return;
      known[el.id] = true;
      var node = document.createElementNS(NS, el.tag);
      var attrs = el.attrs || {{}};
      Object.keys(attrs).forEach(function(k) {{
        node.setAttribute(k, attrs[k]);
      }});
      if (el.text != null) node.textContent = el.text;
      node.classList.add("arbor-anim");
      svg.appendChild(node);
      requestAnimationFrame(function() {{ node.classList.add("shown"); }});
    }});
  }}

  window.addEventListener("message", function(e) {{
    var msg = e.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "branch_partial") {{
      try {{ applySnapshot(msg.data); }} catch(err) {{ console.error("branch_partial patch failed", err); }}
    }} else if (msg.type === "tree_complete") {{
      if (msg.data && msg.data.preview_url) {{
        window.location.replace(msg.data.preview_url);
      }}
    }}
  }});
}})();
</script>
</body>
</html>"""


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
