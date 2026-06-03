# Analysis stage matrix

All LLM stages prepend [`_shared/analysis-preamble.system.txt`](./_shared/analysis-preamble.system.txt).

Context is a **selective user/assistant volley** (see [context-padding.md](../cross-cutting/context-padding.md)), not a blind dump of `analysis_state.json`.

**Model tiers (target):** [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md). **Orchestration (spec):** [llm-orchestration.md](../cross-cutting/llm-orchestration.md). **Gap-fill + validation:** [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md). **Pins:** [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

When `gap_fill_context` is present in stage input, prompts must emit patch-only `artifacts` for listed `gaps` (see preamble).

## Shared analysis

| Stage | Prompt | Tier | Volley | artifacts | Memory sync |
|-------|--------|------|--------|-----------|-------------|
| speaker_roles | understanding/speaker-roles | flagship | full | speakers.json | speakers list |
| content_context | understanding/content-context | flagship | full / shard / collate | content_brief.json | narrative_patch, themes_append, entities_append, confidence_patch |
| boundary_detection | segmentation/boundary-detection | flagship | full / shard / collate | boundaries.json | segment_summary_patch |
| segment_classification | segmentation/segment-classification | flagship | full / shard / collate | manifest.json | themes_append segment_ids |
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
| elevenlabs_prompt_craft | sound_design/elevenlabs-prompt-craft | flagship | full |
| highlight_selection | selection/highlight-selection | flagship | full / shard / collate |
| sfx_brief | assembly/sfx-brief | flagship | full |

## Flow 3

| Stage | Prompt | Tier | Volley | artifacts | Memory sync |
|-------|--------|------|--------|-----------|-------------|
| podcast_show_description | publishing/podcast-show-description | flagship | full | show_description.json | narrative_patch.audience, confidence_patch.show_description |
| export_show_description | — | — | — | show_description.md | — |

## Meta

| Stage | Prompt | Tier | Volley |
|-------|--------|------|--------|
| `_arbiter` | _shared/arbiter | economy | minimal |

Contract: [llm-arbiter-contract.md](./_shared/llm-arbiter-contract.md).

## Specialist post-passes (`analysis.specialists.enabled`)

| Parent stage | Specialist | Output artifact | Investigation trigger |
|--------------|------------|-----------------|------------------------|
| `missing_framing` | `comprehension_risk_blind` | `comprehension_risks[]` | High `risk_score` → `gap_unresolved` |
| `segment_classification` | `theme_coverage_pass` | `segment_topic_patches[]` | Non-empty patches → `theme_unmapped` |
| `topic_coverage_audit` | `emphasis_coverage_pass` | `emphasis_coverage.gaps[]` | Non-empty gaps → coverage re-audit |

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
