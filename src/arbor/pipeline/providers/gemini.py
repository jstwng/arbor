"""Gemini provider plugin (google-genai SDK)."""
from __future__ import annotations

from typing import Iterator

from google import genai
from google.genai import types


class GeminiPlugin:
    name = "gemini"

    def extract(
        self,
        prompt: str,
        system: str,
        schema: dict,
        model_id: str,
        api_key: str,
        temperature: float = 0.3,
    ) -> str:
        if not api_key:
            raise RuntimeError(
                "Gemini API key not configured. Open the portal settings (gear icon) "
                "or edit ~/.config/arbor/config.json."
            )
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        )
        resp = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=config,
        )
        text = resp.text or ""
        if not text.strip():
            raise RuntimeError(f"Gemini returned empty response: {resp!r}")
        return text

    def extract_stream(
        self,
        prompt: str,
        system: str,
        schema: dict,
        model_id: str,
        api_key: str,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        # Phase 1 fallback: synchronous wrapper. Phase 3 replaces this with real streaming.
        yield self.extract(prompt, system, schema, model_id, api_key, temperature)
