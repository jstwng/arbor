"""Anthropic provider plugin (anthropic SDK, tool-use for structured output)."""
from __future__ import annotations

import json
from typing import Iterator

import anthropic


TREE_TOOL_NAME = "submit_tree"


class AnthropicPlugin:
    name = "anthropic"

    def _tool_def(self, schema: dict) -> dict:
        return {
            "name": TREE_TOOL_NAME,
            "description": "Submit the structured branching tree.",
            "input_schema": schema,
        }

    def extract(self, prompt, system, schema, model_id, api_key, temperature=0.3) -> str:
        if not api_key:
            raise RuntimeError(
                "Anthropic API key not configured. Open the portal settings (gear icon) "
                "or edit ~/.config/arbor/config.json."
            )
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model_id,
            max_tokens=8192,
            temperature=temperature,
            system=system,
            tools=[self._tool_def(schema)],
            tool_choice={"type": "tool", "name": TREE_TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use" and getattr(block, "name", "") == TREE_TOOL_NAME:
                return json.dumps(block.input)
        raise RuntimeError("Anthropic returned no tool_use block")

    def extract_stream(self, prompt, system, schema, model_id, api_key, temperature=0.3) -> Iterator[str]:
        if not api_key:
            raise RuntimeError(
                "Anthropic API key not configured. Open the portal settings (gear icon) "
                "or edit ~/.config/arbor/config.json."
            )
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=model_id,
            max_tokens=8192,
            temperature=temperature,
            system=system,
            tools=[self._tool_def(schema)],
            tool_choice={"type": "tool", "name": TREE_TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", "")
                if etype == "input_json_delta":
                    yield event.partial_json
                elif etype == "content_block_stop":
                    block = getattr(event, "content_block", None)
                    if block and getattr(block, "type", "") == "tool_use":
                        accumulated = getattr(block, "input", None)
                        if accumulated is not None:
                            # Some SDK paths produce a complete object here; emit the rest as JSON.
                            # Skip if we already streamed deltas.
                            return
