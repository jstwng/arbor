"""Pipeline events. Every layer yields these."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompactionStarted:
    strategy: str
    chunk_count: int


@dataclass
class ChunkSummarized:
    index: int
    total: int
    summary: str


@dataclass
class CompactionFinished:
    compact_prose_chars: int


@dataclass
class ExtractionStarted:
    provider: str
    model_id: str


@dataclass
class TextDelta:
    text: str


@dataclass
class BranchPartial:
    index: int
    branch: dict[str, Any]
    cumulative_tree: dict[str, Any]


@dataclass
class ValidationRetry:
    reason: str
    attempt: int


@dataclass
class TreeComplete:
    tree: dict[str, Any]


@dataclass
class PipelineError:
    where: str
    message: str
