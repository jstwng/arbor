"""Public pipeline API."""
from __future__ import annotations

import json
from typing import Any

from . import prompts
from .providers import get_plugin
from ..config import get_model, provider_api_key


# Recursive JSON schema for a tree node. Depth limit is enforced through the
# prompt; structured-output validators don't support recursive $ref well.
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


def extract_tree(
    prose: str,
    root_override: str | None,
    model_id: str,
    config: dict[str, Any],
    layers: int = 3,
) -> dict[str, Any]:
    """Provider-aware tree extraction. Same public signature as the old extract.py.

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

    plugin = get_plugin(provider)
    system = prompts.system_prompt_for(layers)
    user_prompt = _build_user_prompt(prose, root_override)

    raw = plugin.extract(
        prompt=user_prompt,
        system=system,
        schema=GEMINI_RESPONSE_SCHEMA,
        model_id=model_id,
        api_key=api_key,
    )

    try:
        tree = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Provider returned non-JSON: {raw!r}") from exc

    if root_override:
        tree["root"] = root_override
    tree["layers"] = layers
    return tree
