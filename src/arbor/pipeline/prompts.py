"""System prompts for the extraction pipeline."""
from __future__ import annotations


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

Schema: every node is {{"label": "...", "children": [...]}}. Leaves have no children (or an empty array). The tree must be exactly {layers} layers deep along every path -- no shallower, no deeper.

Return only valid JSON matching the response schema. Do not include any commentary.
"""

LAYER_GUIDES: dict[int, str] = {
    2: "- Layer 1: root\n- Layer 2: leaf entries (short descriptive lines)",
    3: "- Layer 1: root\n- Layer 2: section labels\n- Layer 3: leaf entries under each section",
    4: "- Layer 1: root\n- Layer 2: part labels\n- Layer 3: section labels under each part\n- Layer 4: leaf entries under each section",
    5: "- Layer 1: root\n- Layer 2: book/volume labels\n- Layer 3: part labels\n- Layer 4: section labels\n- Layer 5: leaf entries",
}


SUMMARIZE_PROMPT = """Extract the 5-10 most important specific ideas from this passage.

Output STRICT JSON in the shape:
{"summary": ["idea 1", "idea 2", ...]}

Each idea should be one tight sentence. Be specific, not generic. Preserve concrete
nouns, names, and numbers. No commentary outside the JSON.
"""


RETRY_PROMPT_PREFIX = """Your previous output violated a rule:
{reason}

Here is the offending tree:
{previous_tree}

Regenerate the tree fixing only the violation. Keep the rest unchanged where possible.
"""


def system_prompt_for(layers: int) -> str:
    """Return the formatted system prompt for the given layer count."""
    layers = max(2, min(5, layers))
    return SYSTEM_PROMPT_TEMPLATE.format(
        layers=layers,
        layers_minus_one=layers - 1,
        layer_guide=LAYER_GUIDES[layers],
    )


def layer_guide_for(layers: int) -> str:
    """Return the layer guide string for the given layer count."""
    layers = max(2, min(5, layers))
    return LAYER_GUIDES[layers]
