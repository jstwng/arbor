"""OpenAI provider plugin (openai SDK, json_schema response format)."""
from __future__ import annotations

from typing import Iterator

from openai import OpenAI


class OpenAIPlugin:
    name = "openai"
    _base_url: str | None = None

    def _client(self, api_key: str) -> OpenAI:
        if self._base_url:
            return OpenAI(api_key=api_key, base_url=self._base_url)
        return OpenAI(api_key=api_key)

    def _response_format(self, schema: dict) -> dict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "tree",
                "schema": schema,
                "strict": False,
            },
        }

    def _messages(self, prompt: str, system: str) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def extract(self, prompt, system, schema, model_id, api_key, temperature=0.3) -> str:
        if not api_key:
            raise RuntimeError(
                "OpenAI API key not configured. Open the portal settings (gear icon) "
                "or edit ~/.config/arbor/config.json."
            )
        client = self._client(api_key)
        resp = client.chat.completions.create(
            model=model_id,
            temperature=temperature,
            messages=self._messages(prompt, system),
            response_format=self._response_format(schema),
        )
        return resp.choices[0].message.content or ""

    def extract_stream(self, prompt, system, schema, model_id, api_key, temperature=0.3) -> Iterator[str]:
        if not api_key:
            raise RuntimeError(
                "OpenAI API key not configured. Open the portal settings (gear icon) "
                "or edit ~/.config/arbor/config.json."
            )
        client = self._client(api_key)
        stream = client.chat.completions.create(
            model=model_id,
            temperature=temperature,
            messages=self._messages(prompt, system),
            response_format=self._response_format(schema),
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text
