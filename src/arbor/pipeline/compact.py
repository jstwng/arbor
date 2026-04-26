"""Compaction layer: shrinks input prose before tree extraction."""
from __future__ import annotations

import json
from typing import Any

from .events import (
    ChunkSummarized,
    CompactionFinished,
    CompactionStarted,
)
from . import prompts
from .providers.base import Plugin


PASS_THROUGH_THRESHOLD = 15_000
MAP_REDUCE_1_THRESHOLD = 100_000
CHUNK_TARGET_CHARS = 8_000
CHUNK_OVERLAP_CHARS = 400

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "array", "items": {"type": "string"}}},
    "required": ["summary"],
}


def pick_strategy(prose: str) -> str:
    n = len(prose)
    if n <= PASS_THROUGH_THRESHOLD:
        return "pass_through"
    if n <= MAP_REDUCE_1_THRESHOLD:
        return "map_reduce_1"
    return "map_reduce_recursive"


def chunk_prose(prose: str) -> list[str]:
    if len(prose) <= CHUNK_TARGET_CHARS:
        return [prose]
    chunks: list[str] = []
    i = 0
    n = len(prose)
    while i < n:
        end = min(i + CHUNK_TARGET_CHARS, n)
        if end < n:
            window = prose.rfind(". ", i + CHUNK_TARGET_CHARS - 500, end)
            if window > i:
                end = window + 2
        chunks.append(prose[i:end])
        if end >= n:
            break
        i = max(end - CHUNK_OVERLAP_CHARS, i + 1)
    return chunks


def _summarize_chunk(
    plugin: Plugin, chunk: str, model_id: str, api_key: str
) -> list[str]:
    raw = plugin.extract(
        prompt=f"PASSAGE:\n{chunk}",
        system=prompts.SUMMARIZE_PROMPT,
        schema=SUMMARY_SCHEMA,
        model_id=model_id,
        api_key=api_key,
    )
    data = json.loads(raw)
    return list(data.get("summary", []))


def compact_to_text(
    prose: str,
    plugin: Plugin,
    model_id: str,
    api_key: str,
    on_event=None,
    force_strategy: str | None = None,
) -> str:
    """Run the chosen strategy and return compacted prose.

    `on_event(evt)` receives CompactionStarted / ChunkSummarized / CompactionFinished
    events as they happen. Caller forwards to SSE (or ignores).

    `force_strategy`: if set, bypasses `pick_strategy` and uses this strategy directly.
    Valid values: "pass_through", "map_reduce_1", "map_reduce_recursive".
    """

    def emit(evt: Any) -> None:
        if on_event is not None:
            on_event(evt)

    strategy = force_strategy if force_strategy is not None else pick_strategy(prose)
    if strategy == "pass_through":
        emit(CompactionStarted(strategy="pass_through", chunk_count=1))
        emit(CompactionFinished(compact_prose_chars=len(prose)))
        return prose

    chunks = chunk_prose(prose)
    emit(CompactionStarted(strategy=strategy, chunk_count=len(chunks)))
    summaries: list[str] = []
    for i, chunk in enumerate(chunks):
        bullets = _summarize_chunk(plugin, chunk, model_id, api_key)
        joined = "\n".join(f"- {b}" for b in bullets)
        emit(ChunkSummarized(index=i, total=len(chunks), summary=joined))
        summaries.append(joined)

    combined = "\n\n".join(summaries)

    if strategy == "map_reduce_recursive" and len(combined) > PASS_THROUGH_THRESHOLD:
        return compact_to_text(combined, plugin, model_id, api_key, on_event=on_event, force_strategy=force_strategy)

    emit(CompactionFinished(compact_prose_chars=len(combined)))
    return combined
