"""Provider plugin protocol."""
from __future__ import annotations

from typing import Iterator, Protocol


class Plugin(Protocol):
    name: str

    def extract_stream(
        self,
        prompt: str,
        system: str,
        schema: dict,
        model_id: str,
        api_key: str,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        """Yield raw text chunks. Concatenation must be a JSON string matching `schema`.
        Plugin handles its own structured-output strategy."""
        ...

    def extract(
        self,
        prompt: str,
        system: str,
        schema: dict,
        model_id: str,
        api_key: str,
        temperature: float = 0.3,
    ) -> str:
        """Non-streaming convenience: return the full text. Default implementations
        can simply concatenate `extract_stream`."""
        ...
