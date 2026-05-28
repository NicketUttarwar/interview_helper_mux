# Analysis stage matrix

All LLM stages prepend [`_shared/analysis-preamble.system.txt`](./_shared/analysis-preamble.system.txt).

Context is a **selective user/assistant volley** (see [context-padding.md](../cross-cutting/context-padding.md)), not a blind dump of `analysis_state.json`.

**Model tiers (target):** [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md). **Orchestration (spec):** [llm-orchestration.md](../cross-cutting/llm-orchestration.md). **Pins:** [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

## Shared analysis

| Stage | Prompt | Tier | Volley | artifacts | Memory sync |
|-------|--------|------|--------|-----------|-------------|
| speaker_roles | understanding/speaker-roles | economy | full | speakers.json | speakers list |
| content_context | understanding/content-context | economy | full | content_brief.json | narrative_patch, themes_append, entities_append, confidence_patch |
| boundary_detection | segmentation/boundary-detection | standard | full / shard / collate | boundaries.json | segment_summary_patch |
| segment_classification | segmentation/segment-classification | standard | full / shard / collate | manifest.json | themes_append segment_ids |
| sound_design_palettes | sound_design/theme-palettes | flagship | full | sound_design_plan.json (coherence + palettes) | follow_up_investigations.theme_unmapped |
| missing_framing | interviewer-gap/missing-framing | flagship | full / shard / collate | gap_evaluations.json | gaps_summary_patch |
| optimal_questions | interviewer-gap/optimal-questions | flagship | full | gap_report.json | major_questions_append, gaps_summary_patch |

## Flow 1 / Flow 2

Flow stages use the same envelope and read `analysis_state_summary`; BUILD-073 adds arbiter evaluation per attempt (and optional uptier retry).

| Stage | Prompt | Tier | Volley |
|-------|--------|------|--------|
| topic_coverage_audit | selection/topic-coverage-audit | flagship | full |
| narrative_arc_plan | selection/narrative-arc-plan | flagship | full |
| full_master_ranking | selection/full-master-ranking | flagship | full |
| transitions | assembly/transitions | economy | full |
| podcast_sfx_brief | assembly/podcast-sfx-brief | economy | full |
| highlight_selection | selection/highlight-selection | flagship | full |
| sfx_brief | assembly/sfx-brief | economy | full |

## Flow 3

| Stage | Prompt | Tier | Volley | artifacts | Memory sync |
|-------|--------|------|--------|-----------|-------------|
| podcast_show_description | publishing/podcast-show-description | flagship | full | show_description.json | narrative_patch.audience, confidence_patch.show_description |

## Meta

| Stage | Prompt | Tier | Volley |
|-------|--------|------|--------|
| `_arbiter` | _shared/arbiter | economy | minimal |

Contract: [llm-arbiter-contract.md](./_shared/llm-arbiter-contract.md).

## Typical investigations

| kind | Trigger | Suggested rerun |
|------|---------|-----------------|
| theme_unmapped | Topic in brief, no segments | segment_classification |
| segment_ambiguity | Overlapping boundaries | boundary_detection |
| gap_unresolved | High-severity gap | missing_framing |

Prefer **shard/collate** over investigations when the issue is payload size/truncation — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

## Example packs

Good vs bad patterns for many stages live under [`_shared/examples/`](./_shared/examples/). Index: [prompts README — Example packs](./README.md#example-packs).
