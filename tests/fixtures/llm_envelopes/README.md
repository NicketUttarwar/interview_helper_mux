# Golden LLM envelopes (lint regression)

Minimal envelope JSON files used by `tests/test_llm_envelope_fixtures.py` to assert `deterministic_lint` rejects known-bad primary outputs without live API calls.

## Suites

| Suite | Test function | Mocks `_lint_generic` |
|-------|---------------|------------------------|
| Stage-only | `test_golden_envelope_stage_lint` | Yes — isolates stage-specific `_LINTERS` |
| Full-stack | `test_golden_envelope_full_stack_lint` | No — exercises generic rubric keys end-to-end |

## Fixture catalog

| File | Stage | Failure mode |
|------|-------|--------------|
| `boundary_detection_empty.json` | `boundary_detection` | Empty boundaries |
| `boundary_detection_truncation_no_decompose.json` | `boundary_detection` | `truncation_requires_decompose` (full-stack) |
| `content_brief_reanchor_bad_seg.json` | `content_brief_reanchor` | Orphan segment ref |
| `content_context_empty_thesis.json` | `content_context` | Empty thesis |
| `content_context_low_confidence.json` | `content_context` | `confidence_gte_min` (full-stack) |
| `edl_narrative_audit_bad_verdict.json` | `edl_narrative_audit` | Bad QC verdict |
| `elevenlabs_prompt_craft_short.json` | `elevenlabs_prompt_craft` | Short prompt |
| `full_master_ranking_orphan.json` | `full_master_ranking` | Orphan selection id |
| `highlight_selection_over_cap.json` | `highlight_selection` | Over cap |
| `missing_framing_low_coverage.json` | `missing_framing` | `segment_coverage_ratio` (full-stack) |
| `missing_framing_no_evals.json` | `missing_framing` | No evaluations |
| `narrative_arc_empty_chapter.json` | `narrative_arc_plan` | Empty chapter |
| `optimal_questions_high_gap.json` | `optimal_questions` | High gap severity |
| `podcast_show_description_word_count.json` | `podcast_show_description` | Word count |
| `podcast_sfx_brief_legacy.json` | `podcast_sfx_brief` | Legacy brief |
| `segment_classification_mono_type.json` | `segment_classification` | Mono type |
| `sfx_brief_over_cap.json` | `sfx_brief` | Over cap |
| `sound_design_palettes_no_identity.json` | `sound_design_palettes` | No sonic identity |
| `sound_design_plan_flow1_over_cap.json` | `sound_design_plan_flow1` | Over cap |
| `sound_design_plan_flow2_over_cap.json` | `sound_design_plan_flow2` | Over cap |
| `speaker_roles_all_unknown.json` | `speaker_roles` | All unknown roles |
| `topic_coverage_audit_no_score.json` | `topic_coverage_audit` | No score |
| `transitions_too_long.json` | `transitions` | Too long transition |

Add a file per stage when introducing a new lint rule; name as `<stage_key>_<failure_mode>.json`.
