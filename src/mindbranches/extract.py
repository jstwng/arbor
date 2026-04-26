"""Convert free-form prose into a branching tree.

Provider-agnostic: dispatches on the configured model's ``provider`` field.
Today only ``gemini`` is wired up. To add another provider, write a
``_extract_<provider>`` function and add a branch in ``extract_tree``.
"""

from __future__ import annotations

import json
from typing import Any

from .config import get_model, provider_api_key

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

GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
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


def _build_user_prompt(prose: str, root_override: str | None) -> str:
    parts: list[str] = []
    if root_override:
        parts.append(f"Use this exact root concept: {root_override!r}.\n\n")
    parts.append(f"Prose:\n\n{prose.strip()}")
    return "".join(parts)


def _extract_gemini(
    prose: str,
    root_override: str | None,
    model_id: str,
    api_key: str,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError(
            "Gemini API key not configured. Open the portal settings (gear icon) "
            "or edit ~/.config/mindbranches/config.json."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_id,
        contents=_build_user_prompt(prose, root_override),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GEMINI_RESPONSE_SCHEMA,
            temperature=0.3,
        ),
    )

    text = response.text or ""
    if not text.strip():
        raise RuntimeError(f"Gemini returned empty response: {response!r}")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned non-JSON: {text!r}") from exc


def extract_tree(
    prose: str,
    root_override: str | None,
    model_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Provider-aware tree extraction.

    Args:
        prose: free-form input text.
        root_override: if given, used verbatim as the root; the model only fills branches.
        model_id: an id present in config["models"] (e.g. "gemini-2.5-flash").
        config: full loaded config dict.
    """
    model = get_model(config, model_id)
    provider = model["provider"]
    api_key = provider_api_key(config, provider)

    if provider == "gemini":
        tree = _extract_gemini(prose, root_override, model_id, api_key)
    else:
        raise RuntimeError(
            f"Provider {provider!r} not implemented yet. "
            f"Add a handler in mindbranches/extract.py to enable it."
        )

    if root_override:
        tree["root"] = root_override
    return tree
