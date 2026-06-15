# Arbiter stage rubrics — index

Per-stage editorial rubrics for the economy-tier LLM arbiter (`_arbiter`). Each JSON file names one `stage_key` from `STAGE_ARTIFACT_SCHEMAS` in `src/interview_mux/prompt_validation.py`.

**Loader:** `src/interview_mux/arbiter_expectations.py` → `docs/prompts/_shared/arbiter-rubrics/<stage_key>.json`  
**Contract:** [llm-arbiter-contract.md](./llm-arbiter-contract.md) · [arbiter.system.txt](./arbiter.system.txt)  
**Format spec:** [arbiter-rubrics/README.md](./arbiter-rubrics/README.md)

The arbiter **routes only** — it does not rewrite artifacts. Verdicts: `accept`, `retry_uptier`, `decompose`, `enqueue_investigation`.

---

## Rubric index

### P0 — Foundation

| Stage | Rubric file | Severity | Decompose |
|-------|-------------|----------|-----------|
| `speaker_roles` | [speaker_roles.json](./arbiter-rubrics/speaker_roles.json) | low | no |
| `content_context` | [content_context.json](./arbiter-rubrics/content_context.json) | high | yes |
| `boundary_detection` | [boundary_detection.json](./arbiter-rubrics/boundary_detection.json) | medium | yes |
| `segment_classification` | [segment_classification.json](./arbiter-rubrics/segment_classification.json) | medium | yes |
| `content_brief_reanchor` | [content_brief_reanchor.json](./arbiter-rubrics/content_brief_reanchor.json) | medium | yes |

### P1 — Narrative

| Stage | Rubric file | Severity | Decompose |
|-------|-------------|----------|-----------|
| `missing_framing` | [missing_framing.json](./arbiter-rubrics/missing_framing.json) | high | yes |
| `optimal_questions` | [optimal_questions.json](./arbiter-rubrics/optimal_questions.json) | high | no |
| `topic_coverage_audit` | [topic_coverage_audit.json](./arbiter-rubrics/topic_coverage_audit.json) | high | yes |
| `narrative_arc_plan` | [narrative_arc_plan.json](./arbiter-rubrics/narrative_arc_plan.json) | high | no |
| `full_master_ranking` | [full_master_ranking.json](./arbiter-rubrics/full_master_ranking.json) | high | yes |
| `edl_narrative_audit` | [edl_narrative_audit.json](./arbiter-rubrics/edl_narrative_audit.json) | high | no |

### P2 — Sound design

| Stage | Rubric file | Severity | Decompose |
|-------|-------------|----------|-----------|
| `sound_design_palettes` | [sound_design_palettes.json](./arbiter-rubrics/sound_design_palettes.json) | low | no |
| `sound_design_plan_flow1` | [sound_design_plan_flow1.json](./arbiter-rubrics/sound_design_plan_flow1.json) | high | no |
| `sound_design_plan_flow2` | [sound_design_plan_flow2.json](./arbiter-rubrics/sound_design_plan_flow2.json) | high | no |
| `sfx_prompt_craft` | [sfx_prompt_craft.json](./arbiter-rubrics/sfx_prompt_craft.json) | low | no |
| `podcast_sfx_brief` | [podcast_sfx_brief.json](./arbiter-rubrics/podcast_sfx_brief.json) | low | no |
| `sfx_brief` | [sfx_brief.json](./arbiter-rubrics/sfx_brief.json) | low | no |

### P3 — Polish

| Stage | Rubric file | Severity | Decompose |
|-------|-------------|----------|-----------|
| `transitions` | [transitions.json](./arbiter-rubrics/transitions.json) | low | no |
| `highlight_selection` | [highlight_selection.json](./arbiter-rubrics/highlight_selection.json) | high | yes |
| `podcast_show_description` | [podcast_show_description.json](./arbiter-rubrics/podcast_show_description.json) | high | no |

---

## Severity bands

| Severity | Editorial impact if wrong | Stages |
|----------|---------------------------|--------|
| **high** | Listener confusion, wrong master, or wasted API spend | `content_context`, `missing_framing`, `optimal_questions`, `topic_coverage_audit`, `narrative_arc_plan`, `full_master_ranking`, `edl_narrative_audit`, `highlight_selection`, `sound_design_plan_flow1`, `sound_design_plan_flow2`, `podcast_show_description` |
| **medium** | Downstream patch cost; decompose often fixes | `boundary_detection`, `segment_classification`, `content_brief_reanchor` |
| **low** | Operator-recoverable or spend-adjacent | `speaker_roles`, `sound_design_palettes`, `transitions`, `sfx_prompt_craft`, `podcast_sfx_brief`, `sfx_brief` |

---

## Deterministic lint keys (cross-rubric)

Pre-arbiter checks in `src/interview_mux/deterministic_lint.py`. Rubrics list applicable keys in `deterministic_lint_keys`.

| Key | Meaning |
|-----|---------|
| `envelope_status_complete` | Envelope `status` is `complete` |
| `schema_errors_empty` | No material JSON Schema errors |
| `producer_artifact_complete` | On-disk artifact passes completeness |
| `segment_coverage_ratio` | Fraction of manifest segments referenced |
| `truncation_flags_absent` | No volley truncation flags |
| `truncation_requires_decompose` | Truncation + decompose-eligible → must not accept |
| `cross_artifact_refs_valid` | `segment_id` refs exist upstream |
| `upstream_artifacts_complete` | Preflight paths present |
| `min_row_count_met` | List artifacts meet minimum rows |
| `confidence_gte_min` | Envelope confidence ≥ rubric floor |

---

## Verdict quick reference

| Situation | Verdict |
|-----------|---------|
| Criteria met; lint pass; confidence ≥ `min_confidence_on_accept` | `accept` |
| Parseable but weak; flagship retries remain | `retry_uptier` |
| `decompose_eligible` + truncation or partial timeline | `decompose` + `shard_plan` |
| Wrong upstream; non-decomposable failure | `enqueue_investigation` |

---

## Stages without arbiter rubrics

Non-LLM stages, meta, and specialists do not have rubric files:

- `_arbiter` (uses compact contract, not a producer rubric)
- `comprehension_risk_blind`, `theme_coverage_pass`, `emphasis_coverage_pass` (specialist passes)
- `transcript_review`, `disfluency_extract`, `source_acoustic_profile`, `mix_flow*`, `mmaudio_sfx_flow*`

---

## Adding a rubric

1. Create `arbiter-rubrics/<stage_key>.json` per [README.md](./arbiter-rubrics/README.md).
2. Add a row to the tier table above.
3. Register lint handler in `deterministic_lint.py` if needed.
4. Update [stage-quality-scorecard.md](../../cross-cutting/stage-quality-scorecard.md).

**Related:** [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §11 · [llm-guidance-program.md](../../cross-cutting/llm-guidance-program.md)
