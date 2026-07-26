# Analysis memory (per interview)

**LLM client:** `openai` version — [anchored-toolchain.md](./anchored-toolchain.md). Model IDs — [model-routing.md](./model-routing.md).

Every execution builds a **custom analysis profile** for that recording. Memory is stored on disk and padded into every LLM call so later stages see themes, questions, style, and open investigations from earlier passes.

**Generation and validation:** Structured artifacts and profile fields are produced by **OpenAI flagship** stages with incremental **gap-fill** (patch only missing fields). Every disk write is validated against JSON Schema; the GUI uses generated Zod schemas before save. Full spec: [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).

## Primary files (operator-editable)

| Path | Purpose |
|------|---------|
| `understanding/analysis_state.json` | **Main profile** — themes, major questions, style, narrative, entities, completion |
| `understanding/investigation_queue.json` | Open items the orchestrator may re-run stages to resolve |
| `understanding/coherence_report.json` | H-ORC-03 scored risks (30m+ interviews) — see [coherence-orc03.md](./coherence-orc03.md) |
| `analysis_state.coherence_risks[]` | Open subset mirrored from coherence report for stage panels / volley caps |
| `understanding/content_brief.json` | Stage artifact (thesis, topics, typed claims, `topic_relationships`); synced into `analysis_state` — pass 1 from `content_context`, timeline patch from `content_brief_reanchor` |
| `understanding/speakers.json` | Speaker roles, early `conversation_profile`, `gap_sensitivity`, optional `conversation_hypotheses` |
| `segments/manifest.json` | Segment timeline |

Edit these in the **Interview profile** GUI panel or any stage JSON editor. Saves run **Zod** (client) + **jsonschema** (server) validation — see [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).

**Stage outputs** in the GUI show each artifact as `pending`, `partial`, or `complete`. Use **Fill gaps** on partial rows to re-run the producing stage, or **Open** to edit manually.

For `content_brief.json`: **complete** after `content_context` means thesis + topics are filled; after `content_brief_reanchor` completes, completeness also requires `topics[].segment_ids` and `topic_relationships`. Open hypotheses from pass 1 live in `analysis_state.hypotheses` until reanchor confirms or rejects them via `memory_updates`.

**Zero-shot + review:** The pipeline runs automatically stage-by-stage, but **stops after each step** that writes custom-run profile JSON until you **Acknowledge & continue** ([operator-gates.md](../workflows/operator-gates.md#gui-operator-console-checkpoints--api-consent)). Re-writing a profile file (LLM or manual save) clears the prior ack for that stage so you can review again.

After edits, use **Redo from selected stage** to re-run downstream LLM stages with your changes. Flow 3 (`REMOVED_podcast_show_description`) reads the same profile slice as Flow 1 ranking — verification is strongly recommended before generating show copy.

### Operator verification

Set `meta.operator_verified: true` in `analysis_state.json` (or click **Mark profile verified** in the GUI) when themes, questions, and style are correct. LLM stages treat verified fields as authoritative.

### Style and identity (`content_context`)

`content_context` emits `memory_updates.interview_identity_patch` (`one_line_summary`, optional `title`) and `style_patch`:

| Field | Purpose |
|-------|---------|
| `style.tone` | Free-text editorial voice (nuance) |
| `style.tone_class` | Enum aligned with Flow 3 show description: `journalistic`, `conversational`, `investor`, `technical`, `human_interest` |
| `style.format_class` | Interview shape: `one_on_one`, `panel`, `fireside`, `technical_deep_dive`, `media_profile`, `debate` |
| `style.pacing`, `interviewer_style`, `interviewee_style`, `format_notes` | Downstream transitions, gaps, highlights, sound design |

`content_brief_reanchor` may refine pacing/tone prose when segment evidence supports it; it should not rewrite `tone_class` / `format_class` without strong contradiction.

If the LLM omits `one_line_summary`, `sync_content_brief_to_state` derives it from `content_brief.thesis`.

### Operator field locks

GUI profile saves record edited paths in `meta.operator_locked_fields`. Locked fields (and all profile style/identity fields when `operator_verified`) are not overwritten by later LLM `style_patch` / `interview_identity_patch` merges. Conflicts enqueue `style_conflict` investigations in `investigation_queue.json`.

## Supporting files (machine-managed)

| Path | Purpose |
|------|---------|
| `understanding/context_index.json` | **Volley memory index (v2)** — synced `stage_plans`, `volley_entries[]`, `padding_rules`, `artifacts_registry`; runtime brain for `build_message_volley` when `prefer_index_over_legacy_summaries` is enabled |
| `understanding/analysis_orchestration.json` | Iteration limits and per-stage attempt counts |
| `understanding/stage_runs/<stage>/attempt_NNN.json` | Full LLM envelopes (audit) |

## What gets sent to OpenAI

Not the whole memory file. `stage_input_helpers.py` selects prior conclusions, profile slices, and shaped stage JSON per step. When enabled, `context_resolver.py` reads active entries from `context_index.json` instead of only `meta.stage_summaries`. Padding knobs live under [`analysis.context.*`](./config-keys.md#analysiscontext).

## Volley entries (context_index v2)

On arbiter-accept merge, the pipeline appends structured entries:

| `kind` | Written when | Used by |
|--------|--------------|---------|
| `stage_conclusion` | `reasoning_summary` accepted | Prior assistant turns (`full` / `collate` profiles) |
| `profile_digest` | `memory_updates` or operator profile save | Profile user turns |
| `investigation` | Investigation queue enqueue | Investigation user turns |
| `shard_summary` | Shard/collate decompose | Collate assistant turns |
| `specialist_finding` | Specialist post/pre passes | Downstream priors |
| `local_framing` | MLX volley compression | Audit only (optional) |

**Invalidation:** `invalidate_stage_summaries()` and manifest cross-validate mark matching entries `invalidated`. Re-accept supersedes prior `stage_conclusion` for the same stage.

**Operator edit:** GUI Pipeline → **Volley** sub-tab; edits set `operator_edited: true` and clear downstream handoff acks for edited upstream conclusions.

**Backfill:** `python tools/backfill_volley_index.py --run-id <exec_id>` from `stage_runs/` + `stage_summaries`.

## Merge rules

- `memory_updates` from each LLM response are **merged** into `analysis_state.json` (append themes/questions/entities by `id`; patch narrative/style).
- Stage artifacts (`content_brief.json`, etc.) remain the canonical output for assembly; sync helpers copy key fields into memory.
- **Incremental persist:** `merge_artifact()` deep-merges LLM patches into existing files; `gap_fill_context` tells the model which fields are already satisfied.
- Operator edits to `analysis_state.json` are **not** overwritten silently — conflicting model updates should surface as `needs` with `type: operator`. When `meta.operator_verified: true`, merge skips protected profile keys (`themes`, `major_questions`, `narrative`, `style`).

**Arbiter merge (BUILD-073):** Do **not** merge memory when the LLM arbiter rejects a primary response (`retry_uptier`, mid-flight `decompose`, or `enqueue_investigation`). Merge only after `accept` or successful collate.

## Per-interview customization

No two interviews share memory. A new `exec_NNN_*` run starts from an empty profile template; analysis discovers themes and style from **that** transcript only.

See [config-keys.md](./config-keys.md#analysiscontext) for padding knobs and [llm-stage-model-matrix.md](./llm-stage-model-matrix.md) for per-stage model routing.
