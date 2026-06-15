# Analysis stage matrix

All LLM stages prepend [`_shared/analysis-preamble.system.txt`](./_shared/analysis-preamble.system.txt).

Context is a **selective user/assistant volley** (see [context-padding.md](../cross-cutting/context-padding.md)), not a blind dump of `analysis_state.json`.

**Model tiers (target):** [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md). **Orchestration (spec):** [llm-orchestration.md](../cross-cutting/llm-orchestration.md). **Gap-fill + validation:** [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md). **Pins:** [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

When `gap_fill_context` is present in stage input, prompts must emit patch-only `artifacts` for listed `gaps` (see preamble).

## Shared analysis

| Stage | Prompt | Tier | Volley | artifacts | Memory sync |
|-------|--------|------|--------|-----------|-------------|
| speaker_roles | understanding/speaker-roles | flagship | full | speakers.json | speakers list |
| content_context | understanding/content-context | flagship | full / shard / collate | content_brief.json | narrative_patch, interview_identity_patch, style_patch, themes_append, entities_append, hypotheses_append, confidence_patch |
| boundary_detection | segmentation/boundary-detection | flagship | full / shard / collate | boundaries.json | segment_summary_patch |
| segment_classification | segmentation/segment-classification | flagship | full / shard / collate | manifest.json | themes_append segment_ids |
| content_brief_reanchor | understanding/content-brief-reanchor | flagship | full / shard / collate | content_brief.json (patch) | themes_append segment_ids, hypotheses_append confirm/reject, style_patch (optional refine), confidence_patch |
| sound_design_palettes | sound_design/theme-palettes | flagship | full | sound_design_plan.json (coherence + palettes) | follow_up_investigations.theme_unmapped |
| missing_framing | interviewer-gap/missing-framing | flagship | full / shard / collate | gap_evaluations.json | gaps_summary_patch |
| optimal_questions | interviewer-gap/optimal-questions | flagship | full | gap_report.json | major_questions_append, gaps_summary_patch |

## Flow 1 / Flow 2

Flow stages use the same envelope and read `analysis_state_summary`; arbiter runs after each primary attempt (uptier retry capped at 2 per stage per run).

| Stage | Prompt | Tier | Volley |
|-------|--------|------|--------|
| topic_coverage_audit | selection/topic-coverage-audit | flagship | full / shard / collate |
| narrative_arc_plan | selection/narrative-arc-plan | flagship | full |
| full_master_ranking | selection/full-master-ranking | flagship | full / shard / collate |
| edl_narrative_audit | selection/edl-narrative-audit | flagship | full |
| transitions | assembly/transitions | flagship | full |
| podcast_sfx_brief | assembly/podcast-sfx-brief | flagship | full |
| sound_design_plan_flow1 | sound_design/plan-flow1 | flagship | full |
| sound_design_plan_flow2 | sound_design/plan-flow2 | flagship | full |
| sfx_prompt_craft | sound_design/sfx-prompt-craft | flagship | full |
| highlight_selection | selection/highlight-selection | flagship | full / shard / collate |
| sfx_brief | assembly/sfx-brief | flagship | full |

## Flow 3

| Stage | Prompt | Tier | Volley | artifacts | Memory sync |
|-------|--------|------|--------|-----------|-------------|
| podcast_show_description | publishing/podcast-show-description | flagship | full | show_description.json | narrative_patch.audience, confidence_patch.show_description |
| export_show_description | — | — | — | show_description.md | — |

[^flow3]: **Analysis-only entry:** Flow 3 runs after G2 with `selected_flow: flow3`. Requires shared analysis complete (`require_analysis_artifacts_complete`) but **not** Flow 1 ranking or Flow 2 selection. Preflight for `podcast_show_description` checks `content_brief.json`, `speakers.json`, and `manifest.json` when flow3 is selected (`llm_preflight.py`). `export_show_description` is deterministic markdown export — no LLM call.

## Meta

| Stage | Prompt | Tier | Volley |
|-------|--------|------|--------|
| `_arbiter` | _shared/arbiter | economy | minimal |

Contract: [llm-arbiter-contract.md](./_shared/llm-arbiter-contract.md).

## Specialist post-passes (`analysis.specialists.enabled`)

Timing: **pre** runs before the parent primary LLM call; **post** runs after the parent stage completes (`llm_specialists.py`).

| Parent stage | Timing | Specialist | Output artifact | Investigation trigger |
|--------------|--------|------------|-----------------|------------------------|
| `missing_framing` | pre | `comprehension_risk_blind` | `comprehension_risks[]` | High `risk_score` → `gap_unresolved` |
| `segment_classification` | post | `theme_coverage_pass` | `segment_topic_patches[]` | Non-empty patches → `theme_unmapped` |
| `topic_coverage_audit` | post | `emphasis_coverage_pass` | `emphasis_coverage.gaps[]` | Non-empty gaps → coverage re-audit |
| `full_master_ranking` | post | `comprehension_risk_blind` | `comprehension_risks[]` | High `risk_score` → `comprehension_risk` / `gap_unresolved` |

Enrichment inputs: see [context-padding.md](../cross-cutting/context-padding.md#stage-enrichment-inputs-stage_enrichmentpy).

## Typical investigations

| kind | Trigger | Suggested rerun |
|------|---------|-----------------|
| theme_unmapped | Topic in brief, no segments | segment_classification |
| segment_ambiguity | Overlapping boundaries | boundary_detection |
| gap_unresolved | High-severity gap | missing_framing |

Prefer **shard/collate** over investigations when the issue is payload size/truncation — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

## Example packs

Good vs bad patterns for many stages live under [`_shared/examples/`](./_shared/examples/). Index: [prompts README — Example packs](./README.md#example-packs).
