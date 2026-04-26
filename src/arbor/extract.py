"""Convert free-form prose into a branching tree.

Provider-agnostic: dispatches on the configured model's ``provider`` field.
Today only ``gemini`` is wired up. To add another provider, write a
``_extract_<provider>`` function and add a branch in ``extract_tree``.
"""

from __future__ import annotations

import json
from typing import Any

from .config import get_model, provider_api_key

SYSTEM_PROMPT_TEMPLATE = """You convert prose into a hierarchical mind-map structure for the Arbor visual format.

You will produce a tree of EXACTLY {layers} layers. Layer 1 is the root concept. The deepest layer (layer {layers}) carries the actual ideas. The intermediate layers are short category labels that group those ideas.

Layer guide for this run (layers = {layers}):
{layer_guide}

Length guidance per layer:
- Layer 1 (root): 1-6 words. A short title for the whole work.
- Top intermediate layers (2..{layers_minus_one}): 1-4 words. They are pill labels that read as parallel categories.
- Leaf layer ({layers}): one tight clause or short sentence (6-16 words). Concrete and specific -- a claim, finding, definition, or recommendation -- not a bullet fragment, but also not a paragraph. Aim for ideas dense enough to stand alone on a slide.

Other rules:
- Every non-leaf node must have at least 2 children.
- Sibling labels at any layer should be parallel in form and at the same level of abstraction.
- Avoid redundancy across siblings.
- Order siblings logically (chronological, hierarchical, or by importance).
- If a root override is provided in the user message, use it verbatim.

Schema: every node is `{{"label": "...", "children": [...]}}`. Leaves have no children (or an empty array). The tree must be exactly {layers} layers deep along every path -- no shallower, no deeper.

Return only valid JSON matching the response schema. Do not include any commentary.
"""

LAYER_GUIDES: dict[int, str] = {
    2: "- Layer 1: root\n- Layer 2: leaf entries (short descriptive lines)",
    3: "- Layer 1: root\n- Layer 2: section labels\n- Layer 3: leaf entries under each section",
    4: "- Layer 1: root\n- Layer 2: part labels\n- Layer 3: section labels under each part\n- Layer 4: leaf entries under each section",
    5: "- Layer 1: root\n- Layer 2: book/volume labels\n- Layer 3: part labels\n- Layer 4: section labels\n- Layer 5: leaf entries",
}

# Recursive JSON schema for a tree node. We encode the depth limit through
# the prompt text since most providers' structured-output validators do not
# support recursive `$ref`. The schema stays loose; the prompt enforces depth.
NODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["label"],
    "properties": {
        "label": {"type": "string"},
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label"],
                "properties": {
                    "label": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["label"],
                            "properties": {
                                "label": {"type": "string"},
                                "children": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["label"],
                                        "properties": {
                                            "label": {"type": "string"},
                                            "children": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "required": ["label"],
                                                    "properties": {
                                                        "label": {"type": "string"},
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["root", "branches"],
    "properties": {
        "root": {"type": "string"},
        "branches": {
            "type": "array",
            "minItems": 2,
            "items": NODE_SCHEMA,
        },
    },
}


def _build_user_prompt(prose: str, root_override: str | None) -> str:
    parts: list[str] = []
    if root_override:
        parts.append(f"Use this exact root concept: {root_override!r}.\n\n")
    parts.append(f"Prose:\n\n{prose.strip()}")
    return "".join(parts)


def _system_prompt_for(layers: int) -> str:
    layers = max(2, min(5, layers))
    return SYSTEM_PROMPT_TEMPLATE.format(
        layers=layers,
        layers_minus_one=layers - 1,
        layer_guide=LAYER_GUIDES[layers],
    )


def _extract_gemini(
    prose: str,
    root_override: str | None,
    model_id: str,
    api_key: str,
    layers: int,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError(
            "Gemini API key not configured. Open the portal settings (gear icon) "
            "or edit ~/.config/arbor/config.json."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_id,
        contents=_build_user_prompt(prose, root_override),
        config=types.GenerateContentConfig(
            system_instruction=_system_prompt_for(layers),
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
    layers: int = 3,
) -> dict[str, Any]:
    """Provider-aware tree extraction.

    Args:
        prose: free-form input text.
        root_override: if given, used verbatim as the root; the model only fills branches.
        model_id: an id present in config["models"] (e.g. "gemini-2.5-flash").
        config: full loaded config dict.
        layers: total tree depth, 2 to 5. Layer 1 is the root, layer N is leaves.
    """
    model = get_model(config, model_id)
    provider = model["provider"]
    api_key = provider_api_key(config, provider)

    if provider == "gemini":
        tree = _extract_gemini(prose, root_override, model_id, api_key, layers)
    else:
        raise RuntimeError(
            f"Provider {provider!r} not implemented yet. "
            f"Add a handler in arbor/extract.py to enable it."
        )

    if root_override:
        tree["root"] = root_override
    tree["layers"] = layers
    return tree
