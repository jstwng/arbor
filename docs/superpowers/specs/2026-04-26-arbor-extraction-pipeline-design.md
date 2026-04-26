# Arbor: provider-agnostic extraction pipeline

**Status:** approved 2026-04-26
**Builds on:** `2026-04-22-arbor-design.md` (v1 architecture)
**Reference:** patterns adapted from huggingface/ml-intern (context compaction, streaming)

## Goal

Replace `extract.py`'s single-provider, single-shot Gemini call with a layered streaming pipeline that:

1. Works across LLM providers (Gemini, Anthropic, OpenAI, OpenAI-compatible local models) through one plugin interface.
2. Auto-scales to input size: pass-through for short prose, single-pass map-summarize for medium, recursive map-reduce for book-length input. Inspired by ml-intern's context compaction.
3. Streams the tree to the portal as it grows. The diagram literally builds in the iframe as JSON arrives from the model.
4. Constrains the deepest layer to 5-6 children per parent (leaf-fanout).
5. Falls out cleanly: any provider plugin is ~30-50 LOC; new ones drop in without touching the rest of the pipeline.

## Non-goals

- Output caching by content hash. Useful but separate concern; lives in a future spec.
- Multi-provider racing or speculative generation.
- Provider-side prompt caching (Anthropic / OpenAI / Gemini cache APIs). Out of scope; rely on each SDK's defaults.
- Replacing Playwright. PNG rendering stays as is.

## Architecture

```
                            prose.txt
                                |
                                v
             +-------------------------------------+
             |  Compaction layer                   |
             |    auto_strategy(byte_count) ->     |
             |      pass_through | map_reduce_1    |
             |      | map_reduce_recursive         |
             +-------------------------------------+
                                |
                                v
             +-------------------------------------+
             |  Provider layer (pluggable)         |
             |    extract_stream(prose, schema)    |
             |    plugins: gemini, anthropic,      |
             |             openai, openai_compat   |
             +-------------------------------------+
                                |
                                v
             +-------------------------------------+
             |  Stream wrapper                     |
             |    incremental JSON parse           |
             |    -> emit branch_partial events    |
             |    -> validate + retry on failures  |
             +-------------------------------------+
                                |
                                v
                          tree.json (live-grown)
                                |
                                v
                     layout -> svg -> live iframe
                          (DOM patched per
                           branch_partial event)
```

Every layer is `Iterator[TreeEvent]` in, `Iterator[TreeEvent]` out, so they compose.

## Module layout

```
src/arbor/
  extract.py              # public API: extract_tree() unchanged signature, internals rewritten
  pipeline/
    __init__.py
    events.py             # TreeEvent dataclasses
    compact.py            # compaction layer
    stream.py             # incremental JSON parser + stream wrapper
    validate.py           # schema + leaf-fanout enforcement
    providers/
      __init__.py         # registry: PROVIDERS[name] -> Plugin
      base.py             # Plugin protocol
      gemini.py           # google-genai
      anthropic.py        # anthropic SDK, tool-use for structured output
      openai.py           # openai SDK, response_format=json_schema
      openai_compat.py    # generic OpenAI-compatible endpoint (Ollama, vLLM, LM Studio)
```

`server.py` consumes the new event stream and forwards it as SSE; `static/` gets a live-iframe template that DOM-patches the SVG as `branch_partial` events arrive.

## Event taxonomy

`pipeline/events.py` defines:

```python
@dataclass
class CompactionStarted:
    strategy: str          # "pass_through" | "map_reduce_1" | "map_reduce_recursive"
    chunk_count: int

@dataclass
class ChunkSummarized:
    index: int
    total: int
    summary: str           # for the optional debug panel; UI doesn't have to render

@dataclass
class CompactionFinished:
    compact_prose_chars: int

@dataclass
class ExtractionStarted:
    provider: str
    model_id: str

@dataclass
class TextDelta:
    text: str              # raw streamed chunk, unparsed

@dataclass
class BranchPartial:
    index: int             # branches[index] just became parsable
    branch: dict           # full subtree at this index
    cumulative_tree: dict  # current full {root, branches} so far

@dataclass
class ValidationRetry:
    reason: str            # which rule failed: "leaf_fanout_low" | "schema" | ...
    attempt: int

@dataclass
class TreeComplete:
    tree: dict             # final validated tree

@dataclass
class PipelineError:
    where: str             # "compaction" | "extraction" | "validation"
    message: str
```

`server.py` forwards each event to the SSE stream as `{"type": "<class_name>", "payload": {...}}`. Backward compat: existing v1 events (`extracting_tree`, `tree_ready`, etc.) are kept as aliases that map to `ExtractionStarted` / `TreeComplete` so the current frontend keeps working during rollout.

## Provider plugin interface

```python
# pipeline/providers/base.py
class Plugin(Protocol):
    name: str

    def extract_stream(
        self,
        prompt: str,
        schema: dict,
        model_id: str,
        api_key: str,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        """Yield raw text chunks. Final concatenation must be a JSON string
        matching `schema`. Plugin handles its own structured-output strategy
        (json_mode, tool_use, json_schema, raw text). Stream errors raise."""
```

Per-provider strategy:

| Provider | Structured-output strategy | Streaming API |
|----------|----------------------------|---------------|
| `gemini` | `response_mime_type="application/json"` + `response_schema` | `models.generate_content_stream` |
| `anthropic` | tool-use with the tree schema as the tool's input schema | `messages.stream`, accumulate `input_json_delta` |
| `openai` | `response_format={"type": "json_schema", ...}` | `chat.completions.create(stream=True)` |
| `openai_compat` | `response_format={"type": "json_object"}` + schema in system prompt | same as `openai` |

Registry:

```python
# pipeline/providers/__init__.py
PROVIDERS: dict[str, type[Plugin]] = {
    "gemini": GeminiPlugin,
    "anthropic": AnthropicPlugin,
    "openai": OpenAIPlugin,
    "openai_compat": OpenAICompatPlugin,
}
```

Config (`~/.config/arbor/config.json`) gains optional sections:

```json
{
  "providers": {
    "gemini":         {"api_key": "..."},
    "anthropic":      {"api_key": "..."},
    "openai":         {"api_key": "..."},
    "openai_compat":  {"base_url": "http://localhost:11434/v1", "api_key": "ollama"}
  },
  "models": [
    {"id": "gemini-2.5-flash",  "label": "Gemini 2.5 Flash",  "provider": "gemini",        "default": true},
    {"id": "claude-haiku-4-5",  "label": "Claude Haiku 4.5",  "provider": "anthropic"},
    {"id": "gpt-5",             "label": "GPT-5",             "provider": "openai"},
    {"id": "llama3.1:8b",       "label": "Llama 3.1 8B (local)", "provider": "openai_compat"}
  ]
}
```

The Settings UI already has provider rows and a model table — wire them through to the new providers, no UI redesign needed.

## Compaction layer

`pipeline/compact.py`:

```python
THRESHOLDS = {
    "pass_through":         15_000,    # ~3k words: send as-is
    "map_reduce_1":        100_000,    # ~20k words: one pass of chunk-summarize, then extract
    # else: recursive map-reduce
}

CHUNK_TARGET_CHARS = 8_000   # ~1500 words per chunk
CHUNK_OVERLAP_CHARS = 400    # carry sentence-context between chunks
```

**`pass_through`:** No compaction. Yield `CompactionStarted("pass_through", 1)`, hand prose to provider directly.

**`map_reduce_1`:** Split prose into N overlapping chunks. For each chunk, call provider with prompt: *"Extract the 5-10 main ideas from this passage as a bulleted list. Be specific."* Each chunk yields a `ChunkSummarized` event. Concatenate summaries into "compacted prose," then run normal tree extraction on it.

**`map_reduce_recursive`:** Same as `map_reduce_1`, but if combined summaries are still over `pass_through` threshold, recurse: re-chunk the summaries, summarize the summaries, and so on, until under threshold. Yield events at each recursion level.

The compaction layer calls the provider plugin via the same `extract_stream` interface — but with a non-tree schema (`{"summary": [str, ...]}`). One plugin handles both modes.

## Stream wrapper + incremental JSON

`pipeline/stream.py`:

The provider yields raw text chunks (`TextDelta` events forwarded to UI for the "what is the model saying" debug pane). A small state-machine accumulator buffers them and tries to parse on each chunk:

```python
def parse_branches_incremental(buffer: str) -> Iterator[tuple[int, dict]]:
    """Yield (index, branch_dict) for each `branches[i]` object that has just
    become a complete, valid JSON value. Tolerates trailing junk."""
```

Implementation: track brace depth, locate `"branches"` array, scan for top-level objects in that array, parse each with `json.loads` once it's complete. When a new branch index becomes parsable, emit `BranchPartial` with the cumulative tree so far.

Edge cases handled:
- Provider streams text with markdown fences (`” `json ... ` ”`) — strip before parsing.
- Provider streams diff-style tokens that include partial unicode escapes — wait until balanced.
- Provider returns JSON in single chunk (no streaming benefit) — still emit one `BranchPartial` per branch in order so UI logic stays uniform.

## Validation + leaf-fanout enforcement

`pipeline/validate.py`:

```python
LEAF_FANOUT_MIN = 5
LEAF_FANOUT_MAX = 6
MAX_RETRIES = 1
```

After `TreeComplete`, check:
1. **Schema:** every node has `label`, `children` is list (possibly empty).
2. **Layer cap:** depth <= configured `layers`.
3. **Leaf fanout:** for any node N where every child of N is a leaf (no grandchildren), assert `5 <= len(N.children) <= 6`.

On violation, yield `ValidationRetry(reason, attempt=1)` and re-call the provider with the failing tree included in the prompt and explicit correction instructions:

> *"Your previous output violated the leaf-fanout rule: parent X has Y leaves; expected 5-6. Regenerate the tree."*

If retry also fails: for `leaf_fanout_high`, truncate to 6. For `leaf_fanout_low`, keep as-is and emit a warning event but don't block the user.

The system prompt itself is updated to state the rule explicitly so most outputs comply on first pass:

> *"The deepest layer (parents-of-leaves) must have between 5 and 6 leaf children per parent. Intermediate layers should have 2-4 children."*

## Live tree assembly UX

The portal's iframe currently loads a static `output.html` once `preview_ready` fires. New behavior:

1. On submit, server immediately writes a *skeleton* HTML to the job dir: empty SVG with the cream background, font-loaded, ready to receive children.
2. Server emits `preview_ready` with the skeleton URL — frontend loads the iframe.
3. The skeleton page itself opens its own `EventSource('/status/{job_id}')` connection.
4. As `BranchPartial` events arrive, the page recomputes layout for the cumulative tree (cheap for n<30) and patches its own SVG DOM in place: append `<path>` connector, `<rect>` pill, `<text>` label, then run a 250ms CSS opacity transition.
5. On `TreeComplete`, the page replaces itself with the canonical `output.html` (stable, screenshot-able). Server screenshots the canonical version for PNG.

Layout for partial trees: extend `compute_layout` to take a partial tree (some branches missing) and compute final positions assuming the missing branches will arrive later. Do this by:
- Pre-computing total height assuming branch count from the prompt's `layers` budget — fall back to current count if no signal.
- Reserving vertical slots for branches not yet seen so existing branches don't jump as new ones arrive.

If the layout-stability work is messy in practice, fall back to "re-layout each time, accept jumpiness" (simpler).

## CLI surface

`arbor` CLI gains:

- `--provider {gemini,anthropic,openai,openai_compat}` — explicitly pick the provider for a model id (defaults to the model's configured provider).
- `--no-compact` — force `pass_through` regardless of input size (for debugging).
- `--compact-strategy {auto,pass_through,map_reduce_1,map_reduce_recursive}` — manual override.
- `--no-stream` — non-streaming mode (collect full response, parse once). Useful for non-streaming providers or batch use.

`extract_tree(prose, root_override, model_id, config, layers)` keeps its current signature; the pipeline runs synchronously and returns the final tree. A new `extract_tree_stream(...)` returns the iterator for the portal.

## Backward compatibility

- `extract.py` continues to export `extract_tree(...)` with the same signature. Internally it consumes the new pipeline and returns the final tree synchronously, so the CLI keeps working unchanged.
- Existing SSE event names (`extracting_tree`, `tree_ready`, etc.) are mapped to the new event types. The current `app.js` keeps working until we ship the live-iframe upgrade.
- Existing `~/.config/arbor/config.json` files keep working — providers other than `gemini` are added on first save through Settings.

## Testing

- **Unit:** `parse_branches_incremental` against fixtures of progressive JSON streams (fence-wrapped, escaped strings, trailing whitespace, partial unicode).
- **Unit:** validators against trees that violate each rule.
- **Unit:** `auto_strategy` against byte counts at threshold boundaries.
- **Integration with mocks:** every provider plugin has a `MockPlugin` test — `extract_stream` returns a canned text-chunk iterator, end-to-end pipeline produces expected events.
- **Live smoke:** at least one end-to-end test against the actual default provider (Gemini), gated on `GEMINI_API_KEY`.

## Risks

| Risk | Mitigation |
|------|-----------|
| Incremental JSON parsing flaky across providers | Conservative parser; tests on real streams from each; `--no-stream` escape hatch. |
| Live-iframe DOM patching causes visual jank | Reserve layout slots upfront; if too messy, fall back to "re-layout per branch, accept jumps." |
| Compaction loses signal — final tree gets generic | Surface chunk summaries in a debug panel for inspection; tune chunk size + overlap. |
| Anthropic/OpenAI tool-use returns slightly different field shapes | Per-plugin normalizer; `validate.py` is the single source of truth on output shape. |
| Provider SDK adds latency vs raw HTTP | Acceptable: SDKs handle retries / streaming correctness for free. Revisit if real bottleneck. |

## Milestones (build order)

1. **Plugin interface + Gemini port** (no behavior change). Existing extract.py becomes a thin wrapper around `pipeline.providers.gemini`. Verify v1 still works.
2. **Validation layer + leaf-fanout enforcement.** Drops in immediately; visible in next render.
3. **Stream wrapper + incremental parser.** `BranchPartial` events flow but UI not yet updated — still ships `output.html` once at end.
4. **Live iframe.** Frontend skeleton + DOM patching. Now diagrams grow live.
5. **Compaction layer.** `pass_through` first (cheap), then `map_reduce_1`, then recursion.
6. **Anthropic + OpenAI + openai_compat plugins.** One PR each.
7. **CLI flags + Settings UI updates** for provider switching.

Each milestone ships independently and is reversible.
