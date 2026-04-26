"""CLI entrypoint for the mindbranches generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import default_model_id, default_theme_id, load_config
from .extract import extract_tree
from .layout import compute_layout
from .render import write_outputs


def main() -> None:
    config = load_config()
    model_choices = [m["id"] for m in config.get("models", [])]
    theme_choices = [t["id"] for t in config.get("themes", [])]
    default_model = default_model_id(config)
    default_theme = default_theme_id(config)
    default_width = config.get("defaults", {}).get("width", 1600)

    parser = argparse.ArgumentParser(
        prog="mindbranches",
        description="Generate MindBranches-style diagrams from prose.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to a .txt file (or tree.json with --from-tree).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("./out"),
        help="Output directory.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Override the LLM-chosen root concept.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=default_width,
        help=f"Canvas width in px (default {default_width}).",
    )
    parser.add_argument(
        "--theme",
        choices=theme_choices,
        default=default_theme,
        help=f"Theme id (default {default_theme}).",
    )
    parser.add_argument(
        "--model",
        choices=model_choices,
        default=default_model,
        help=f"Model id from config (default {default_model}).",
    )
    parser.add_argument(
        "--from-tree",
        action="store_true",
        help="Skip extraction; treat input as tree.json.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    if args.from_tree:
        tree = json.loads(args.input.read_text())
    else:
        prose = args.input.read_text().strip()
        if not prose:
            print("Error: input file is empty.", file=sys.stderr)
            sys.exit(1)
        print(f"Extracting tree via {args.model}...", flush=True)
        tree = extract_tree(
            prose, root_override=args.root, model_id=args.model, config=config
        )

    print(
        f"Computing layout (theme={args.theme}, width={args.width})...",
        flush=True,
    )
    layout = compute_layout(tree, width=args.width, theme=args.theme)

    print(f"Rendering outputs to {args.out}...", flush=True)
    paths = write_outputs(tree, layout, args.out)
    for name, path in paths.items():
        print(f"  {name}: {path}")
