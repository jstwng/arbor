"""Tests for the compaction layer (compact.py)."""
from __future__ import annotations

import pytest

from arbor.pipeline.compact import (
    CHUNK_OVERLAP_CHARS,
    CHUNK_TARGET_CHARS,
    chunk_prose,
    pick_strategy,
)


def test_pick_strategy_short():
    assert pick_strategy("x" * 10_000) == "pass_through"


def test_pick_strategy_medium():
    assert pick_strategy("x" * 50_000) == "map_reduce_1"


def test_pick_strategy_long():
    assert pick_strategy("x" * 200_000) == "map_reduce_recursive"


def test_chunk_prose_respects_target_size():
    # Build prose longer than one chunk to force multiple chunks
    prose = "word " * 10_000  # ~50k chars
    chunks = chunk_prose(prose)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= CHUNK_TARGET_CHARS + CHUNK_OVERLAP_CHARS


def test_chunk_prose_overlaps():
    prose = "x" * (CHUNK_TARGET_CHARS * 3)
    chunks = chunk_prose(prose)
    assert len(chunks) >= 2
    # Tail of chunk[0] should appear at head of chunk[1]
    overlap_region = chunks[0][-CHUNK_OVERLAP_CHARS:]
    assert chunks[1].startswith(overlap_region)


def test_chunk_prose_short_returns_one():
    assert len(chunk_prose("short text")) == 1
