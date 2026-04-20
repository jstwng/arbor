"""Convert free-form prose into a branching tree via Gemini structured JSON output."""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types

MODEL_MAP = {
    "flash": "gemini-2.5-flash",
    "flash-lite": "gemini-2.5-flash-lite",
}

SYSTEM_PROMPT = """You convert prose into a horizontal mind-map structure for the MindBranches visual format.

Read the input. Identify:
1. A short root concept (1-6 words) that captures the central idea.
2. A handful of branches (categories / facets / sub-themes) that fan from the root. The right number depends on the source -- use as many as the prose actually warrants. Do not pad. Do not over-prune.
3. Under each branch, 2-6 short sub-bullets (3-10 words each) -- concrete points, not paraphrased prose.

Rules:
- Branches must be parallel in nature (same level of abstraction).
- Avoid redundancy across branches.
- Sub-bullets must be short, punchy, factual or concrete. No filler.
- Order branches in a way that reads logically (chronological, hierarchical, or by importance).
- If a root override is provided in the user message, use it verbatim and choose branches that fit it.

Return only valid JSON matching the response schema. Do not include any commentary.
"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["root", "branches"],
    "properties": {
        "root": {"type": "string"},
        "branches": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "required": ["label", "children"],
                "properties": {
                    "label": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


def extract_tree(
    prose: str,
    root_override: str | None = None,
    model: str = "flash",
) -> dict[str, Any]:
    """Call Gemini with structured JSON output to convert prose into a MindBranches tree."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to .env or export it in your shell."
        )

    client = genai.Client(api_key=api_key)
    model_id = MODEL_MAP.get(model, model)

    user_parts: list[str] = []
    if root_override:
        user_parts.append(f"Use this exact root concept: {root_override!r}.\n\n")
    user_parts.append(f"Prose:\n\n{prose.strip()}")

    response = client.models.generate_content(
        model=model_id,
        contents="".join(user_parts),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.3,
        ),
    )

    text = response.text or ""
    if not text.strip():
        raise RuntimeError(f"Gemini returned empty response: {response!r}")

    try:
        tree = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned non-JSON: {text!r}") from exc

    if root_override:
        tree["root"] = root_override
    return tree
