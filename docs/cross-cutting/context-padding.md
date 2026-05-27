# Context padding (selective message volley)

OpenAI calls use a **system prompt** (preamble + stage) plus a **multi-turn user/assistant volley** built by `src/interview_mux/context_volley.py`. Client version: [anchored-toolchain.md](./anchored-toolchain.md). The pipeline does **not** send the full `analysis_state.json` on every call.

**Smart routing (spec):** [llm-orchestration.md](./llm-orchestration.md) adds `full` \| `shard` \| `collate` volley profiles for map-reduce sub-calls. v1 uses `full` only.

## Message structure

| Turn | Role | Contents |
|------|------|----------|
| — | `system` | `_shared/analysis-preamble.system.txt` + stage `.system.txt` |
| 1 | `user` | Current task (one paragraph) |
| 2 | `assistant` | Prior stage conclusions (prose summaries only) |
| 3+ | `user` | Operator profile slice — **only if** relevant fields exist |
| 4+ | `user` | Open investigations — **only** blocking or stage-matched (max 1–3) |
| last | `user` | Shaped JSON — evidence for **this stage only** |

Prior conclusions come from `analysis_state.meta.stage_summaries` or one-line artifact digests. The next stage reads the previous stage’s `reasoning_summary` from the envelope, not the entire memory file.

## Per-stage plan

Defined in `STAGE_PLANS` in `context_volley.py`. Examples:

| Stage | Prior conclusions | Profile slice | Investigations |
|-------|-------------------|---------------|----------------|
| `speaker_roles` | none | operator notes only | none |
| `content_context` | speaker roles | identity, notes | ≤2 blocking |
| `boundary_detection` | speaker roles, content_context | themes, thesis | segment/theme kinds |
| `segment_classification` | content_context, boundary_detection | themes, narrative, speakers | theme/segment kinds |
| `missing_framing` | segment_classification, content_context | narrative, entities, major_questions | gap kinds |
| `optimal_questions` | missing_framing, content_context | style, major_questions, narrative | gap kinds |
| `full_master_ranking` | narrative_arc_plan, topic_coverage_audit, optimal_questions, missing_framing | themes, narrative, style | — |
| `highlight_selection` | content_context, missing_framing | themes, narrative, style, major_questions | ≤1 |
| `transitions` | full_master_ranking, optimal_questions | style, narrative | — |
| `podcast_sfx_brief` | full_master_ranking, narrative_arc_plan | style | — |
| `sfx_brief` | highlight_selection | style, narrative | — |
| `podcast_show_description` | content_context, speaker_roles, segment_classification, missing_framing, optimal_questions | themes, narrative, style, major_questions, entities | gap kinds ≤2 |

See [prompts/analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md). Per-stage volley profile: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md).

## Volley profiles (target)

| Profile | When | Assistant prior turns | Investigations | Input shaping |
|---------|------|----------------------|----------------|---------------|
| `full` | `task_kind=primary` (default) | Yes — prior stage summaries | Yes, capped per `STAGE_PLANS` | Current caps in `analysis.context` |
| `shard` | `task_kind=shard` during decompose | **No** — one-line parent `reasoning_summary` only | None | Tighter per-shard caps; single batch of `segment_ids` |
| `collate` | `task_kind=collate` after shards | Yes — one assistant turn per shard summary | None | Merged compact shard artifacts only |

**Padding rules:**

- Not every call gets full user/assistant banter — only `full` and `collate` include multi-turn prior conclusions.
- `shard` calls must not replay the entire investigation queue or full profile slice; parent stage passes minimal context.
- Arbiter calls use a **minimal** volley (see [llm-arbiter-contract.md](../prompts/_shared/llm-arbiter-contract.md)) — not `STAGE_PLANS`.

Implement in `build_message_volley(..., profile="full"|"shard"|"collate")` — see [llm-orchestration-implementation-handoff.md](./llm-orchestration-implementation-handoff.md).

## Stage data shaping

Heavy fields are stripped per stage:

- Full transcript only on `content_context` and `boundary_detection` (with char caps)
- `missing_framing` gets compact segment list (truncated text), not raw transcript
- `optimal_questions` gets gap evaluations + affected segments only
- Flow stages get slim brief + capped manifest; ranking also gets compact `coverage_audit`, `narrative_plan`, `gap_report`
- `transitions` gets `interviewer_sample_lines` from manifest + `gap_report`
- `podcast_sfx_brief` / `sfx_brief` get compact `selection` (order or highlights), not full transcript
- `podcast_show_description` gets `content_brief`, slim manifest (capped segments with topic tags + truncated text), `speakers`, profile slice, and optional one-line gap summaries — **not** full ranked selection or SFX plans

Limits in `config/app.defaults.json` → `analysis.context`:

```json
"context": {
  "transcript_excerpt_chars": 12000,
  "transcript_full_chars": 36000,
  "segment_text_max_chars": 400,
  "max_segments_in_context": 60,
  "max_stage_data_chars": 32000
}
```

## Audit

Each attempt stores the volley in `understanding/stage_runs/<stage>/attempt_NNN.json` under `context_volley` and `context_chars`.

## Long interviews

When caps truncate evidence, see [long-interview-chunking.md](../workflows/long-interview-chunking.md) for policy and rerun strategy.

## Operator edits

Verified profile fields appear as a dedicated user turn (prose, not full JSON). Re-run the stage that should consume your edits after saving `analysis_state.json`.
