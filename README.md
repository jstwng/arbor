# mindbranches

Generate MindBranches-style horizontal mind-map diagrams from free-form prose.

Pipeline: `prose.txt` -> Claude tool-use -> `tree.json` -> geometry -> `output.svg` + `output.html` + `output.png`.

Reference: https://x.com/MindBranches

## Install

```bash
cd mindbranches
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
echo 'GEMINI_API_KEY=AIza...' > .env
```

## CLI

```bash
mindbranches examples/sample-prose.txt --out ./out
mindbranches notes.txt --theme dark --root "The shape of attention"
mindbranches tree.json --from-tree         # skip extraction, render hand-edited tree
```

Flags:

- `--out PATH` output directory (default `./out`)
- `--root "..."` override the LLM-chosen root concept
- `--width N` canvas width in px (default 1600)
- `--theme cream|dark|mono` (default `cream`)
- `--model flash|flash-lite` (default `flash` -- Gemini 2.5 Flash)
- `--from-tree` interpret input as `tree.json`, skip the API call

Outputs (in `--out`):

- `tree.json` -- hand-editable intermediate
- `output.svg` -- canonical, self-contained (Inter font embedded as base64)
- `output.html` -- browser preview
- `output.png` -- 2x DPI screenshot for posting

## Web portal

```bash
mindbranches-portal              # http://127.0.0.1:8765
mindbranches-portal --port 9000
```

Paste a filepath, pick theme/model/root, watch live status, download outputs.

## Project layout

```
src/mindbranches/
  cli.py        # CLI entrypoint
  server.py     # FastAPI portal + SSE
  extract.py    # Claude tool-use, prose -> tree
  layout.py     # geometry computation
  render.py     # SVG / HTML / PNG rendering
  templates/    # Jinja HTML wrapper
  static/       # portal frontend
  fonts/        # Inter TTFs (bundled, base64-embedded into SVG)
examples/
  sample-prose.txt
docs/superpowers/specs/
  2026-04-22-mindbranches-design.md
```
