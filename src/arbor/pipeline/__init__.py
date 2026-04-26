"""Public pipeline API."""
from __future__ import annotations

import json
from typing import Any, Iterator

from . import prompts
from .events import (
    BranchPartial,
    ExtractionStarted,
    PipelineError,
    TextDelta,
    TreeComplete,
    ValidationRetry,
)
from .providers import get_plugin
from .stream import parse_branches_incremental, strip_fences
from .validate import ValidationFailure, validate_tree, truncate_high_fanout
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


def extract_tree_stream(
    prose: str,
    root_override: str | None,
    model_id: str,
    config: dict[str, Any],
    layers: int = 3,
) -> Iterator[Any]:
    """Streaming tree extraction. Yields TreeEvents as the model responds.

    Events emitted (in order):
      ExtractionStarted, TextDelta* (one per chunk), BranchPartial* (one per
      completed branch), optionally ValidationRetry, then TreeComplete.
    """
    model = get_model(config, model_id)
    provider = model["provider"]
    api_key = provider_api_key(config, provider)
    plugin = get_plugin(provider)

    system = prompts.system_prompt_for(layers)
    user_prompt = _build_user_prompt(prose, root_override)

    yield ExtractionStarted(provider=provider, model_id=model_id)

    buf = ""
    seen = 0
    cumulative: dict[str, Any] = {"root": root_override or "", "branches": []}
    for chunk in plugin.extract_stream(
        prompt=user_prompt,
        system=system,
        schema=GEMINI_RESPONSE_SCHEMA,
        model_id=model_id,
        api_key=api_key,
    ):
        buf += chunk
        yield TextDelta(text=chunk)
        for idx, branch in parse_branches_incremental(buf, already_seen=seen):
            seen = idx + 1
            cumulative["branches"].append(branch)
            yield BranchPartial(
                index=idx,
                branch=branch,
                cumulative_tree={"root": cumulative["root"], "branches": list(cumulative["branches"])},
            )

    final_text = strip_fences(buf)
    try:
        final = json.loads(final_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Provider returned non-JSON: {final_text!r}") from exc

    if root_override:
        final["root"] = root_override
    final["layers"] = layers

    try:
        validate_tree(final, layers=layers)
        yield TreeComplete(tree=final)
        return
    except ValidationFailure as e:
        if e.reason == "leaf_fanout_high":
            yield TreeComplete(tree=truncate_high_fanout(final))
            return
        yield ValidationRetry(reason=str(e), attempt=1)
        retry_user_prompt = (
            user_prompt
            + "\n\n"
            + prompts.RETRY_PROMPT_PREFIX.format(
                reason=str(e),
                previous_tree=json.dumps(final, indent=2),
            )
        )
        retried_raw = plugin.extract(
            prompt=retry_user_prompt,
            system=system,
            schema=GEMINI_RESPONSE_SCHEMA,
            model_id=model_id,
            api_key=api_key,
        )
        try:
            retried = json.loads(retried_raw)
        except json.JSONDecodeError:
            yield TreeComplete(tree=final)  # fall back to first attempt
            return
        if root_override:
            retried["root"] = root_override
        retried["layers"] = layers
        try:
            validate_tree(retried, layers=layers)
        except ValidationFailure as e2:
            if e2.reason == "leaf_fanout_high":
                retried = truncate_high_fanout(retried)
        yield TreeComplete(tree=retried)


def extract_tree(
    prose: str,
    root_override: str | None,
    model_id: str,
    config: dict[str, Any],
    layers: int = 3,
) -> dict[str, Any]:
    """Provider-aware tree extraction with validation and retry. Same public signature as the old extract.py.

    Args:
        prose: free-form input text.
        root_override: if given, used verbatim as the root; the model only fills branches.
        model_id: an id present in config["models"] (e.g. "gemini-2.5-flash").
        config: full loaded config dict.
        layers: total tree depth, 2 to 5. Layer 1 is the root, layer N is leaves.
    """
    final: dict[str, Any] | None = None
    for evt in extract_tree_stream(prose, root_override, model_id, config, layers):
        if isinstance(evt, TreeComplete):
            final = evt.tree
        elif isinstance(evt, PipelineError):
            raise RuntimeError(f"{evt.where}: {evt.message}")
    if final is None:
        raise RuntimeError("Pipeline ended without TreeComplete")
    return final
