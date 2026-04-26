# Arbor Generator -- Design Spec

**Date:** 2026-04-22
**Owner:** Justin Wang
**Status:** Approved

## Purpose

A Python CLI that ingests a free-form `.txt` file of prose and produces a Arbor-style horizontal mind-map diagram in three formats: SVG (canonical), HTML (browser preview), and PNG (post-ready).

Reference account: https://x.com/Arbor -- clean, ink-on-paper branching diagrams used to organize concepts visually. Root concept anchored on the left, category branches fanning to the right, sub-bullets under each branch.

## Non-goals

- No auto-posting to X (manual upload).
- No multi-page diagrams or animation.
- No support for inputs other than `.txt` prose at the input boundary (a JSON tree can be passed via `--from-tree` to skip extraction, but that's an internal escape hatch, not a primary input mode).

## Pipeline

```
input.txt
  -> extract.py    (LLM, structured JSON output -> tree)
  -> tree.json     (intermediate, hand-editable)
  -> layout.py     (geometry: positions, bezier control points)
  -> render.py     (SVG -> HTML wrapper -> PNG via Playwright)
  -> output.{svg,html,png,json}
```

The intermediate `tree.json` is canonical between extraction and rendering. Users can hand-edit it and re-run rendering without re-calling the API.

## Tree schema

```json
{
  "root": "How LLMs Learn",
  "branches": [
    {
      "label": "Pretraining",
      "children": ["Next-token prediction", "Web-scale corpora"]
    },
    {
      "label": "Fine-tuning",
      "children": ["Supervised", "RLHF"]
    },
    {
      "label": "Inference",
      "children": ["Sampling", "Decoding"]
    }
  ]
}
```

- `root`: short title (1-6 words) for the central concept.
- `branches`: ordered list. The number of branches is whatever the LLM judges to fit the source -- no hard cap. Users can edit `tree.json` to trim or reorder.
- `branches[].label`: 1-3 word category title.
- `branches[].children`: list of short descriptive lines (typically 3-10 words each).

## Component responsibilities

### `extract.py`

- Single function: `extract_tree(prose, root_override, model_id, config) -> dict`.
- Provider-aware. Today only `gemini` is wired (via the `google-genai` SDK with native JSON structured output via `response_schema`). Adding `anthropic`, `openai`, or another provider means writing one handler function and adding a dispatch branch.
- Default model: `gemini-2.5-flash`. Other models in the config dropdown.
- If `root_override` is provided, it's passed to the model as a constraint and the model fills only `branches`.
- Writes the result to `tree.json` in the output dir.

### `layout.py`

- Pure function over the tree: `compute_layout(tree, width=1600, theme="cream") -> Layout`.
- Outputs a `Layout` dataclass with:
  - Canvas dimensions (width, computed height).
  - Root rectangle (x, y, w, h).
  - For each branch: pill rect, bezier path string, list of sub-bullet text rows (x, y, text), accent color index.
- Geometry rules:
  - Canvas: configurable width (default 1600px); height computed from total branch content + padding (80px all sides).
  - Root: rounded rect, ~280px wide, vertically centered, with text wrapped if needed.
  - Branches: vertical stack on the right half. Each branch occupies `branch_pill_height + (n_children * sub_bullet_line_height) + inter_branch_padding`. Total stack height = sum of branch heights + (n_branches - 1) * inter_branch_padding. Stack is vertically centered against the root.
  - Bezier from root edge to branch pill: control points at 1/3 and 2/3 of the horizontal gap, smooth fan.
  - Sub-bullets: stacked under each branch pill, left-aligned, line-height 1.5.
- Pure Python; no external graphics deps.

### `render.py`

- `render(layout, theme, out_dir)`:
  1. Builds an SVG string from the `Layout` (templated string concatenation, no SVG library needed -- geometry is simple).
  2. Wraps the SVG in an HTML page (`templates/diagram.html.j2`) that loads the bundled Inter font via `@font-face` and a base CSS reset. The browser renders the SVG verbatim.
  3. Launches Playwright headless Chromium, opens the HTML file, screenshots at 2x DPI (`device_scale_factor=2`).
- Writes `output.svg`, `output.html`, `output.png` to the out dir alongside `tree.json`.

### `cli.py`

- argparse entrypoint installed as `arbor` (via `pyproject.toml` script entry).
- Required positional: `input.txt` (or `tree.json` when `--from-tree` is set).
- Flags:
  - `--out PATH` (default: `./out`)
  - `--root "..."` override LLM root choice
  - `--width N` canvas width (default 1600)
  - `--theme <id>` palette (choices populate from config; default `cream`)
  - `--model <id>` (choices populate from config; default = the model marked default in config)
  - `--from-tree` interpret input as `tree.json`, skip extraction
- Reads provider API keys from `~/.config/arbor/config.json` (auto-migrates from a `.env` `GEMINI_API_KEY` on first run).

## Visual style

**Layout:** horizontal mind map. Root anchored center-left; branches stack vertically on the right; each connected by a smooth bezier. Sub-bullets sit beneath each branch pill, indented, no bullet glyphs.

**Typography:** Inter (Regular, Medium, Bold), bundled in `src/arbor/fonts/`.
- Root: 30px Bold
- Branch label: 20px Medium
- Sub-bullet: 15px Regular, line-height 1.5

**Themes:**

| Theme | Background  | Ink       | Branch accents                                                    |
|-------|-------------|-----------|-------------------------------------------------------------------|
| cream | `#FBF7F0`   | `#1A1A1A` | slate, terracotta, sage, dusty-blue, mauve, mustard (cycled)      |
| dark  | `#161616`   | `#F0EBE3` | same six accents, slightly desaturated for dark-mode readability  |
| mono  | `#FBF7F0`   | `#1A1A1A` | all branch pills use the ink color (no accents)                   |

Accents cycle by index. If there are more than 6 branches, the cycle repeats.

**Lines:** 2px stroke for bezier connectors. Stroke color matches branch accent (cream/dark) or ink (mono).

**No** gradients, drop shadows, glow effects, or rounded-everything aesthetic. Reads as ink-on-paper.

## Stack

- Python 3.11+
- `google-genai` (Gemini SDK, default LLM provider)
- `jinja2` (HTML wrapper template)
- `playwright` (headless Chromium for PNG)
- `fastapi` + `uvicorn` + `sse-starlette` (web portal + live status events)
- `python-multipart` (file upload to portal)
- Inter TTFs bundled in repo

## Folder layout

```
arbor/
  pyproject.toml
  README.md
  docs/superpowers/specs/2026-04-22-arbor-design.md
  src/arbor/
    __init__.py
    cli.py
    config.py
    extract.py
    layout.py
    render.py
    server.py
    static/      # portal frontend
    templates/
      diagram.html.j2
    fonts/
      Inter-Regular.ttf
      Inter-Medium.ttf
      Inter-Bold.ttf
  examples/
    sample-prose.txt
    sample-output.svg
    sample-output.html
    sample-output.png
    sample-output.json
```

## Error handling

- Missing API key for the chosen provider: hard error pointing the user at the portal Settings (gear icon) or `~/.config/arbor/config.json`.
- Empty / whitespace-only input file: hard error.
- LLM returns invalid tree (the schema constrains shape, but if it fails): print the raw response and exit non-zero.
- Playwright not installed: print install hint (`playwright install chromium`) and exit. SVG and HTML are still written even if PNG step fails -- those are produced before the screenshot call.

## Testing

- `tests/test_layout.py`: unit tests over `compute_layout` with hand-written tree fixtures. Verify: no overlaps, root within canvas, bezier endpoints anchored to correct edges.
- `tests/test_extract.py`: skipped by default unless `RUN_API_TESTS=1`. Sanity-checks shape on a small prose fixture.
- Manual: `examples/sample-prose.txt` runs end-to-end and produces visible artifacts. Eyeball check against Arbor reference.

## Web portal

A local FastAPI app that wraps the CLI behind a browser UI. Lets the user paste a filepath or drop a file, watch the pipeline run live, and download the outputs without touching the terminal.

### Endpoints

- `GET /` -- serves `static/index.html`
- `GET /config` -- returns the public config (providers' `has_key` flags, models, themes, defaults). API key values are never sent.
- `POST /config` -- updates API keys, custom models, defaults; persists to disk.
- `POST /convert` -- body: `{ "filepath": "/abs/path/to/input.txt", "theme": "cream", "model": "<id>", "root": null, "width": 1600 }`. Spawns a background job, returns `{ "job_id": "<uuid>" }`.
- `POST /upload` -- multipart form upload. Saves the file to the job dir, then runs the same pipeline.
- `GET /status/{job_id}` -- Server-Sent Events stream. Emits one event per pipeline step. Closes on `done` or `error`.
- `GET /download/{job_id}/{filename}` -- serves any of the four output files for the given job.
- `GET /preview/{job_id}/output.html` -- inline HTML so the browser renders the diagram in a new tab.

### SSE event sequence

Each event is `event: <name>\ndata: <json>\n\n`. Names in order:

1. `queued` -- job created, worker not started yet
2. `reading_file` -- opening the txt file, payload: `{ "size_bytes": N }`
3. `extracting_tree` -- calling the model
4. `tree_ready` -- payload: full `tree.json` content
5. `computing_layout` -- geometry pass
6. `rendering_svg` -- writing SVG
7. `wrapping_html` -- Jinja template applied
8. `preview_ready` -- HTML on disk, frontend can embed it before the PNG step
9. `screenshotting_png` -- Playwright launching, payload: `{ "estimate_seconds": 2 }`
10. `done` -- payload: `{ "outputs": ["tree.json", "output.svg", "output.html", "output.png"] }`
11. `error` -- payload: `{ "step": "<step>", "message": "..." }` (replaces `done` if anything fails)

### Frontend

Single-page UI in `src/arbor/static/`:

- `index.html` -- markup with header, settings gear, file row (text input + Choose file button + drop zone), theme/model/width selects, root override, submit. Status trail and downloads sections are hidden until a job runs.
- `app.js` -- vanilla JS, no framework. Custom dropdown component (replaces native `<select>` so the open menu is fully styled). On submit: POSTs to `/upload` (with held file) or `/convert` (with typed path), opens EventSource on `/status/{job_id}`, drives the live preview and status trail.
- `style.css` -- editorial cream aesthetic. Serif headline (Georgia fallback), Inter for body. Generous whitespace. Status rows fade in as events arrive.

### Job storage

In-memory dict for v1: `jobs[job_id] = {"status": "...", "events": [...], "out_dir": "..."}`. Outputs written to `~/.cache/arbor/<job_id>/`. Old jobs are not auto-cleaned (manual delete if needed).

### Run command

```
arbor-portal              # starts uvicorn on http://127.0.0.1:8765
arbor-portal --port 9000  # custom port
```

## Open issues / deferred

- Auto-posting to X: out of scope for v1. Manual upload of `output.png`.
- Custom fonts: hardcoded to Inter for v1. Could expose `--font` later.
- Sub-branch nesting (3+ levels deep): not supported. Tree is exactly 2 levels (branch + children). Reflects Arbor' actual style.
