"""Shared pytest fixtures for arbor tests."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_prose() -> str:
    return (
        Path(__file__).parent.parent / "examples" / "sample-prose.txt"
    ).read_text()


@pytest.fixture
def sample_tree() -> dict:
    return json.loads(
        (Path(__file__).parent.parent / "examples" / "sample-output.json").read_text()
    )


@pytest.fixture
def small_valid_tree() -> dict:
    """3-layer tree, leaf-fanout valid (5 leaves per leaf-parent)."""
    return {
        "root": "Topic",
        "branches": [
            {
                "label": "Branch A",
                "children": [
                    {"label": "Sub A1", "children": [
                        {"label": "leaf 1"}, {"label": "leaf 2"},
                        {"label": "leaf 3"}, {"label": "leaf 4"},
                        {"label": "leaf 5"},
                    ]},
                ],
            },
        ],
    }
