# Context padding (selective message volley)

OpenAI calls use a **system prompt** (preamble + stage) plus a **multi-turn user/assistant volley** built by `src/interview_mux/context_volley.py`. Client version: [anchored-toolchain.md](./anchored-toolchain.md). The pipeline does **not** send the full `analysis_state.json` on every call.

**Smart routing (shipped):** [llm-orchestration.md](./llm-orchestration.md) adds `full` \| `shard` \| `collate` volley profiles for map-reduce sub-calls on decompose-eligible stages.

**Local framing (shipped):** [local-llm-tier.md](./local-llm-tier.md) — optional MLX pass to compress priors into ≤2 volley turns before OpenAI.

**Volley memory index (shipped):** `understanding/context_index.json` v2 stores queryable `volley_entries` (stage conclusions, investigations, profile digests, shard summaries). Runtime resolution via `context_resolver.py` when `analysis.context_index.prefer_index_over_legacy_summaries` is `true`. GUI: Pipeline → **Volley** sub-tab.

## Message structure

| Turn | Role | Contents |
|------|------|----------|
| — | `system` | `_shared/analysis-preamble.system.txt` + stage `.system.txt` |
| 1 | `user` | Current task (one paragraph) |
| 2 | `assistant` | Prior stage conclusions (prose summaries only) |
| 3+ | `user` | Operator profile slice — **only if** relevant fields exist |
| 4+ | `user` | Open investigations — **only** blocking or stage-matched (max 1–3) |
| last | `user` | Shaped JSON — evidence for **this stage only** (includes `gap_fill_context` when artifact exists or is partial — [artifact-generation-and-validation.md](./artifact-generation-and-validation.md)), plus **Required response format** compact block |

Prior conclusions come from `analysis_state.meta.stage_summaries` or one-line artifact digests. The next stage reads the previous stage’s `reasoning_summary` from the envelope, not the entire memory file.

## Per-stage plan

Defined in `STAGE_PLANS` in `context_volley.py`. Examples:

| Stage | Prior conclusions | Profile slice | Investigations |
|-------|-------------------|---------------|----------------|
| `speaker_roles` | none | operator notes only | none |
| `content_context` | speaker roles | identity, notes | ≤2 blocking |
| `boundary_detection` | speaker roles, content_context | themes, narrative (thesis) | segment/theme kinds |
| `segment_classification` | content_context, boundary_detection | themes, narrative, speakers | theme/segment kinds |
| `content_brief_reanchor` | content_context, segment_classification | themes, narrative, hypotheses | theme kinds ≤2 |
| `sound_design_palettes` | content_context, content_brief_reanchor, segment_classification | themes, narrative, style, operator_notes | theme kinds ≤2 |
| `missing_framing` | segment_classification, content_brief_reanchor, content_context | narrative, entities, major_questions, hypotheses | gap kinds |
| `optimal_questions` | missing_framing, content_context | style, major_questions, narrative | gap kinds |
| `topic_coverage_audit` | content_context, segment_classification, missing_framing, optimal_questions | themes, narrative, major_questions | theme kinds ≤2 |
| `narrative_arc_plan` | topic_coverage_audit, optimal_questions, missing_framing, content_context | themes, narrative, style, major_questions | — |
| `full_master_ranking` | narrative_arc_plan, topic_coverage_audit, optimal_questions, missing_framing | themes, narrative, style | — |
| `highlight_selection` | content_context, missing_framing | themes, narrative, style, major_questions | ≤1 |
| `transitions` | full_master_ranking, optimal_questions | style, narrative | — |
| `sound_design_plan_flow1` | full_master_ranking, narrative_arc_plan, transitions, optimal_questions | style, themes, narrative | — |
| `sound_design_plan_flow2` | highlight_selection | style, themes, narrative | — |
| `edl_narrative_audit` | full_master_ranking, narrative_arc_plan, topic_coverage_audit, transitions, missing_framing, sound_design_plan_flow1 | style, themes, narrative, major_questions | ≤1 |
| `sfx_prompt_craft` | sound_design_plan_flow1, sound_design_plan_flow2 | style, themes, narrative | — |
| `sfx_prompt_refine` | sfx_prompt_craft | style, themes, narrative | — |
| `podcast_sfx_brief` | full_master_ranking, narrative_arc_plan | style | — |
| `sfx_brief` | highlight_selection | style, narrative | — |
| `podcast_show_description` | speaker_roles, content_context, segment_classification, missing_framing, optimal_questions | themes, narrative, style, major_questions, entities | gap kinds ≤2 |

See [prompts/analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md). Per-stage volley profile: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md).

## Volley profiles (shipped)

| Profile | When | Assistant prior turns | Investigations | Input shaping |
|---------|------|----------------------|----------------|---------------|
| `full` | `task_kind=primary` (default) | Yes — prior stage summaries | Yes, capped per `STAGE_PLANS` | Current caps in `analysis.context` |
| `shard` | `task_kind=shard` during decompose | **No** — one-line parent `reasoning_summary` only | None | Tighter per-shard caps; single batch of `segment_ids` |
| `collate` | `task_kind=collate` after shards | Yes — **one assistant turn per shard** (`reasoning_summary` + artifact counts) | None | Merged compact shard payloads in final user turn |

**Padding rules:**

- Not every call gets full user/assistant banter — only `full` and `collate` include multi-turn prior conclusions.
- `shard` calls must not replay the entire investigation queue or full profile slice; parent stage passes minimal context.
- Arbiter calls use a **minimal** volley (see [llm-arbiter-contract.md](../prompts/_shared/llm-arbiter-contract.md)) — not `STAGE_PLANS`.

Implement in `build_message_volley(..., profile="full"|"shard"|"collate")` — see [llm-orchestration-implementation-handoff.md](./llm-orchestration-implementation-handoff.md).

## Stage data shaping

Heavy fields are stripped per stage:

- Full transcript only on `content_context` and `boundary_detection` (with char caps); `content_context` may **proactively shard/collate** when transcript length exceeds `proactive_decompose_chars`
- `speaker_roles` receives `transcript_samples` (opening / middle / closing windows) instead of a single excerpt
- `content_brief_reanchor` gets compact `content_brief` + capped manifest (no raw transcript)
- `missing_framing` gets compact segment list (truncated text), not raw transcript
- `optimal_questions` gets gap evaluations + affected segments only
- Flow stages get slim brief + capped manifest; ranking also gets compact `coverage_audit`, `narrative_plan`, `gap_report`
- `transitions` gets `interviewer_sample_lines` from manifest + `gap_report`
- `sound_design_palettes` gets compact brief + manifest + optional existing SDP stub; no raw transcript
- `sound_design_plan_flow1` / `sound_design_plan_flow2` get compact `sound_design_plan`, selection/highlights, transitions (flow1), not full transcript
- `edl_narrative_audit` gets slim ranking, narrative plan, coverage audit, transitions, gap summaries, SDP plan — not raw transcript
- `sfx_prompt_craft` gets compact SDP `assets[]` and coherence; not full transcript
- `podcast_sfx_brief` / `sfx_brief` get compact `selection` (order or highlights), not full transcript
- `podcast_show_description` gets `content_brief`, slim manifest (capped segments with topic tags + truncated text), `speakers`, profile slice, and optional one-line gap summaries — **not** full ranked selection or SFX plans

**Enrichment keys** (when present): `pause_ladder_hints` (boundary), `emphasis_regions` (coverage/narrative arc), `quotability_signals` (highlights), `value_features_summary` (opt-in), `comprehension_risks` (missing framing after specialist pass). Built by [`stage_enrichment.py`](../../src/interview_mux/stage_enrichment.py).

Limits in `config/app.defaults.json` → `analysis.context`:

```json
"context": {
  "transcript_excerpt_chars": 24000,
  "transcript_full_chars": 72000,
  "speaker_roles_sample_chars": 24000,
  "max_transcript_shards": 12,
  "proactive_decompose_chars": 72000,
  "segment_text_max_chars": 400,
  "max_segments_in_context": 100,
  "max_segments_in_gap_pass": 50,
  "max_gap_evaluations": 50,
  "max_stage_data_chars": 64000,
  "interviewer_sample_lines": 8
}
```

`understanding/context_index.json` (v2) is the **runtime volley brain**: synced `stage_plans`, `padding_rules`, `artifacts_registry`, and append-only `volley_entries[]`. Populated on arbiter-accept merge; backfill via `tools/backfill_volley_index.py`. Char budget defaults mirror `analysis.context` caps.

## Audit

Each attempt stores the volley in `understanding/stage_runs/<stage>/attempt_NNN.json` under `context_volley` and `context_chars`.

**Per API call (full audit):** [llm-call-record-framework.md](./llm-call-record-framework.md) — `understanding/llm_calls/<stage>/attempt_NNN/<seq>_<task_kind>.json` with labeled request, response, and `volley.turns` for copy-paste / rebuild.

## Long interviews

When caps truncate evidence, see [long-interview-chunking.md](../workflows/long-interview-chunking.md) for policy and rerun strategy.

## Operator edits

Verified profile fields appear as a dedicated user turn (prose, not full JSON). Re-run the stage that should consume your edits after saving `analysis_state.json`.

## Interview spine padding (`interview_spine` in stage JSON)

When `interview_spine.enabled`, build inputs attach a compact spine slice via `attach_spine_to_payload()` / `_compact_interview_spine()`:

| Stage | Typical payload |
|-------|-----------------|
| `boundary_detection` | up to 40 `boundary_events`, `speaker_stats` |
| `content_context` | 2 sample windows, 8 events |
| `segment_classification` | 3 windows, 10 events |
| `missing_framing` | 4 windows, 15 events |
| `highlight_selection` | 5 windows, 12 events |
| `full_master_ranking` | 3 windows, 10 events |

Spec: [interview-spine.md](./interview-spine.md).

## Coherence summary padding (`coherence_summary` in stage JSON)

When `coherence.enabled` and interview duration ≥ 30m, build inputs attach `coherence_summary` via `attach_coherence_summary()` / `_compact_coherence_summary()`:

| Stage | Risk cap |
|-------|----------|
| `topic_coverage_audit` | 5 |
| `narrative_arc_plan` | 4 |
| `content_brief_reanchor` | 4 |
| `missing_framing` | 3 |
| `podcast_show_description` | 2 (blocking `claim_contradiction` only) |

Spec: [coherence-orc03.md](./coherence-orc03.md).
