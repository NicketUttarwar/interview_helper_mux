# Analysis stage matrix

All LLM stages prepend [`_shared/analysis-preamble.system.txt`](./_shared/analysis-preamble.system.txt).

Context is a **selective user/assistant volley** (see [context-padding.md](../cross-cutting/context-padding.md)), not a blind dump of `analysis_state.json`.

## Shared analysis

| Stage | Prompt | artifacts | Memory sync |
|-------|--------|-----------|-------------|
| speaker_roles | understanding/speaker-roles | speakers.json | speakers list |
| content_context | understanding/content-context | content_brief.json | narrative_patch, themes_append, entities_append, confidence_patch |
| boundary_detection | segmentation/boundary-detection | boundaries.json | segment_summary_patch |
| segment_classification | segmentation/segment-classification | manifest.json | themes_append segment_ids |
| missing_framing | interviewer-gap/missing-framing | gap_evaluations.json | gaps_summary_patch |
| optimal_questions | interviewer-gap/optimal-questions | gap_report.json | major_questions_append, gaps_summary_patch |

## Flow 1 / Flow 2

Flow stages use the same envelope and read `analysis_state_summary` but do not run the inner retry loop by default (single pass).

| Stage | Prompt |
|-------|--------|
| topic_coverage_audit | selection/topic-coverage-audit |
| narrative_arc_plan | selection/narrative-arc-plan |
| full_master_ranking | selection/full-master-ranking |
| transitions | assembly/transitions |
| podcast_sfx_brief | assembly/podcast-sfx-brief |
| highlight_selection | selection/highlight-selection |
| sfx_brief | assembly/sfx-brief |

## Typical investigations

| kind | Trigger | Suggested rerun |
|------|---------|-----------------|
| theme_unmapped | Topic in brief, no segments | segment_classification |
| segment_ambiguity | Overlapping boundaries | boundary_detection |
| gap_unresolved | High-severity gap | missing_framing |
