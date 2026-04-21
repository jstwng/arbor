"""CLI entrypoint for the mindbranches generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .extract import extract_tree
from .layout import compute_layout
from .render import write_outputs


def main() -> None:
    load_dotenv()

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
        default=1600,
        help="Canvas width in px.",
    )
    parser.add_argument(
        "--theme",
        choices=["cream", "dark", "mono"],
        default="cream",
    )
    parser.add_argument(
        "--model",
        choices=["flash", "flash-lite"],
        default="flash",
        help="Gemini model: flash (gemini-2.5-flash) or flash-lite (cheaper).",
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
        print(f"Extracting tree via Gemini {args.model}...", flush=True)
        tree = extract_tree(prose, root_override=args.root, model=args.model)

    print(
        f"Computing layout (theme={args.theme}, width={args.width})...",
        flush=True,
    )
    layout = compute_layout(tree, width=args.width, theme=args.theme)

    print(f"Rendering outputs to {args.out}...", flush=True)
    paths = write_outputs(tree, layout, args.out)
    for name, path in paths.items():
        print(f"  {name}: {path}")
