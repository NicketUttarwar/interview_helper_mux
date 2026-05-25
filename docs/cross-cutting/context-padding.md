# Context padding (selective message volley)

OpenAI calls use a **system prompt** (preamble + stage) plus a **multi-turn user/assistant volley** built by `src/interview_mux/context_volley.py`. The pipeline does **not** send the full `analysis_state.json` on every call.

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

See [prompts/analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md).

## Stage data shaping

Heavy fields are stripped per stage:

- Full transcript only on `content_context` and `boundary_detection` (with char caps)
- `missing_framing` gets compact segment list (truncated text), not raw transcript
- `optimal_questions` gets gap evaluations + affected segments only
- Flow stages get slim brief + capped manifest; ranking also gets compact `coverage_audit`, `narrative_plan`, `gap_report`
- `transitions` gets `interviewer_sample_lines` from manifest + `gap_report`
- `podcast_sfx_brief` / `sfx_brief` get compact `selection` (order or highlights), not full transcript

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

## Operator edits

Verified profile fields appear as a dedicated user turn (prose, not full JSON). Re-run the stage that should consume your edits after saving `analysis_state.json`.
