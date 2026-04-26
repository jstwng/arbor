"""Generic OpenAI-compatible HTTP endpoint (Ollama, vLLM, LM Studio, ...)."""
from __future__ import annotations

from openai import OpenAI

from .openai import OpenAIPlugin


class OpenAICompatPlugin(OpenAIPlugin):
    name = "openai_compat"

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or "http://localhost:11434/v1"

    def _response_format(self, schema: dict) -> dict:
        # Most local servers don't support json_schema yet. Use the schema in the
        # system prompt (already includes shape info) and ask for plain JSON.
        return {"type": "json_object"}

    def _client(self, api_key: str) -> OpenAI:
        # Local servers usually don't need a real key but the SDK requires the field.
        return OpenAI(api_key=api_key or "local", base_url=self._base_url)
