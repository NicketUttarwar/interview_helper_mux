# Analysis memory (per interview)

**LLM client:** `openai` version — [anchored-toolchain.md](./anchored-toolchain.md). Model IDs — [model-routing.md](./model-routing.md).

Every execution builds a **custom analysis profile** for that recording. Memory is stored on disk and padded into every LLM call so later stages see themes, questions, style, and open investigations from earlier passes.

## Primary files (operator-editable)

| Path | Purpose |
|------|---------|
| `understanding/analysis_state.json` | **Main profile** — themes, major questions, style, narrative, entities, completion |
| `understanding/investigation_queue.json` | Open items the orchestrator may re-run stages to resolve |
| `understanding/content_brief.json` | Stage artifact (thesis, topics, claims); synced into `analysis_state` |
| `understanding/speakers.json` | Speaker roles |
| `segments/manifest.json` | Segment timeline |

Edit these in the **Interview profile** GUI panel or any stage JSON editor. After edits, use **Redo from selected stage** to re-run downstream LLM stages with your changes. Flow 3 (`podcast_show_description`) reads the same profile slice as Flow 1 ranking — verification is strongly recommended before generating show copy.

### Operator verification

Set `meta.operator_verified: true` in `analysis_state.json` (or click **Mark profile verified** in the GUI) when themes, questions, and style are correct. LLM stages treat verified fields as authoritative.

## Supporting files (machine-managed)

| Path | Purpose |
|------|---------|
| `understanding/context_index.json` | Token padding rules and artifact registry |
| `understanding/analysis_orchestration.json` | Iteration limits and per-stage attempt counts |
| `understanding/stage_runs/<stage>/attempt_NNN.json` | Full LLM envelopes (audit) |

## What gets sent to OpenAI

Not the whole memory file. `context_volley.py` selects prior conclusions, profile slices, investigations, and shaped stage JSON per step. See [context-padding.md](./context-padding.md).

## Merge rules

- `memory_updates` from each LLM response are **merged** into `analysis_state.json` (append themes/questions/entities by `id`; patch narrative/style).
- Stage artifacts (`content_brief.json`, etc.) remain the canonical output for assembly; sync helpers copy key fields into memory.
- Operator edits to `analysis_state.json` are **not** overwritten silently — conflicting model updates should surface as `needs` with `type: operator`.

**Arbiter merge (BUILD-073):** Do **not** merge memory when the LLM arbiter rejects a primary response (`retry_uptier`, mid-flight `decompose`, or `enqueue_investigation`). Merge only after `accept` or successful collate — [llm-orchestration.md](./llm-orchestration.md).

## Per-interview customization

No two interviews share memory. A new `exec_NNN_*` run starts from an empty profile template; analysis discovers themes and style from **that** transcript only.

See [context-padding.md](./context-padding.md), [llm-orchestration.md](./llm-orchestration.md), and [workflows/analysis-orchestration-loop.md](../workflows/analysis-orchestration-loop.md).
