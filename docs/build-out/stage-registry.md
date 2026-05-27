# Stage registry

Authoritative list of **every pipeline stage** (shipped, gate, and planned). When adding a stage, update this file, `pipeline.py`, `web/stages.py`, the matching `docs/pipeline/*/README.md`, and [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) in the same PR.

**Code source of truth (shipped orders):** `src/interview_mux/pipeline.py` (`ANALYSIS_ORDER`, `FLOW1_ORDER`, `FLOW2_ORDER`).

---

## Legend

| Status | Meaning |
|--------|---------|
| **shipped** | In `pipeline.py` and runnable |
| **gate** | Operator checkpoint; may not use `.stage_done` |
| **planned** | Spec + ticket; not in `pipeline.py` yet |

---

## Optional — pre-analysis

| Stage id | Status | Module | Ticket | Primary outputs | Prompt / spec |
|----------|--------|--------|--------|-----------------|---------------|
| `audio_preclean` | planned | `stages/audio_preclean.py` | BUILD-019 | `preclean/isolated.wav`, `preclean/lineage.json` | — · [audio_preclean/README.md](../pipeline/audio_preclean/README.md) |

---

## Shared analysis

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `ingest` | shipped | `ingest.py` | BUILD-020 | `ingest/normalized.wav`, `ingest/checksums.json` | — |
| `transcribe` | shipped | `transcribe_aws.py` | BUILD-021 | `transcript/full.json`, `transcript/speakers.json` | — |
| `transcript_review_build` | shipped | `transcript_review.py` | BUILD-018 | `transcript/review_queue.json` | — |
| `transcript_review` | gate | `transcript_review.py` | BUILD-018 | `transcript/corrections.json` | — |
| `speaker_roles` | shipped | `understanding.py` | BUILD-022 | `understanding/speakers.json` | `understanding/speaker-roles` |
| `content_context` | shipped | `understanding.py` | BUILD-023 | `understanding/content_brief.json` | `understanding/content-context` |
| `boundary_detection` | shipped | `segmentation.py` | BUILD-024 | `segments/boundaries.json` | `segmentation/boundary-detection` |
| `segment_classification` | shipped | `segmentation.py` | BUILD-024 | `segments/manifest.json` | `segmentation/segment-classification` |
| `missing_framing` | shipped | `gaps.py` | BUILD-025 | `understanding/gap_evaluations.json` | `interviewer-gap/missing-framing` |
| `optimal_questions` | shipped | `gaps.py` | BUILD-026 | `understanding/gap_report.json`, `interviewer_script.txt` | `interviewer-gap/optimal-questions` |
| `vo_ingest` | shipped | `gaps.py` | BUILD-027 | Merges `vo_pickup/*.wav` into timeline | — |
| `source_acoustic_profile` | planned | `understanding.py` or new | BUILD-082 | `understanding/source_acoustic_profile.json` | TBD · [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) |
| `sound_design_palettes` | planned | `sound_design_stages.py` | BUILD-061 | SDP `palettes`, `coherence` | `sound_design/theme-palettes` |

**GUI-only (not in `ANALYSIS_ORDER`):** `analysis_profile` — edit `analysis_state.json` ([analysis-memory.md](../cross-cutting/analysis-memory.md)).

**Pipeline README:** [capture](../pipeline/capture/README.md) · [ingest](../pipeline/ingest/README.md) · [transcription](../pipeline/transcription/README.md) · [understanding](../pipeline/understanding/README.md) · [segmentation](../pipeline/segmentation/README.md) · [interviewer-gap](../pipeline/interviewer-gap/README.md)

---

## Gates

| Gate id | Status | Module | Ticket | Sets / checks | Doc |
|---------|--------|--------|--------|---------------|-----|
| G0 `transcript_review` | shipped | `gates.py`, `transcript_review.py` | BUILD-017 | STT corrections before `speaker_roles` | [operator-gates.md](../workflows/operator-gates.md) |
| G1 `g1_vo_pickup` | shipped | `gates.py`, `gaps.py` | BUILD-017 | `vo_pickup/` for `delivery: record` | same |
| G2 `g2_flow_select` | partial | `gates.py`, `server.py` | BUILD-017, **080** | `run_meta.selected_flow` — API today: flow1 \| flow2 only | same |

---

## Flow 1 — full master podcast

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `topic_coverage_audit` | shipped | `analysis_flow1_extended.py` | BUILD-029 | `flow_1_master/coverage_audit.json` | `selection/topic-coverage-audit` |
| `narrative_arc_plan` | shipped | `analysis_flow1_extended.py` | BUILD-030 | `flow_1_master/narrative_plan.json` | `selection/narrative-arc-plan` |
| `full_master_ranking` | shipped | `selection_flow1.py` | BUILD-031 | `flow_1_master/selection.json` | `selection/full-master-ranking` |
| `transitions` | shipped | `selection_flow1.py` | BUILD-032 | `flow_1_master/transitions.json` | `assembly/transitions` |
| `podcast_sfx_brief` | shipped (v1) | `selection_flow1.py` | BUILD-033 | `flow_1_master/podcast_sfx_brief.json` | `assembly/podcast-sfx-brief` |
| `sound_design_plan_flow1` | planned | `sound_design_stages.py` | BUILD-062 | SDP `flow_plans.flow1` | `sound_design/plan-flow1` |
| `elevenlabs_sfx_flow1` | shipped (v1) | `sfx_elevenlabs.py` | BUILD-034, **064** | `flow_1_master/sfx/*.wav` | craft: `elevenlabs-prompt-craft` |
| `assembly_preview` | planned | `assembly_flow1.py` | BUILD-069 | `flow_1_master/assembly_preview.wav` | — |
| `edl_flow1` | shipped | `assembly_flow1.py` | BUILD-035, **067** | `flow_1_master/edl.json` | — |
| `mux_flow1` | shipped (v1 speech) | `assembly_flow1.py` | BUILD-035 | `flow_1_master/assembly.wav` | — |
| `mix_flow1` | planned | TBD | BUILD-065 | Replaces/aliases v1 mux | — |
| `master_flow1` | shipped | `mastering.py` | BUILD-036, **071** | `flow_1_master/master.wav` | — |

**README:** [scoring_and_selection](../pipeline/scoring_and_selection/README.md) · [audio_editing](../pipeline/audio_editing/README.md) · [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [mastering_and_export](../pipeline/mastering_and_export/README.md)

---

## Flow 2 — highlight reel

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `highlight_selection` | shipped | `selection_flow2.py` | BUILD-040 | `flow_2_highlights/selection.json` | `selection/highlight-selection` |
| `sfx_brief` | shipped (v1) | `selection_flow2.py` | BUILD-041 | `flow_2_highlights/sfx_brief.json` | `assembly/sfx-brief` |
| `sound_design_plan_flow2` | planned | `sound_design_stages.py` | BUILD-063 | SDP `flow_plans.flow2` | `sound_design/plan-flow2` |
| `elevenlabs_sfx_flow2` | shipped (v1) | `sfx_elevenlabs.py` | BUILD-042, **064** | `flow_2_highlights/sfx/*.wav` | craft stage |
| `mux_flow2` | shipped | `assembly_flow2.py` | BUILD-043 | `flow_2_highlights/assembly.wav` | — |
| `mix_flow2` | planned | TBD | BUILD-065 | Target mix engine | — |
| `master_flow2` | shipped | `mastering.py` | BUILD-044 | `flow_2_highlights/master.wav` | — |

---

## Flow 3 — publishing copy

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `podcast_show_description` | planned | `publishing_flow3.py` | BUILD-045 | `flow_3_description/show_description.json` | `publishing/podcast-show-description` |
| `export_show_description` | planned | `publishing_flow3.py` | BUILD-046 | `flow_3_description/show_description.md` | — |

**Wire-up ticket:** BUILD-080 (`FLOW3_ORDER`, `run_flow3`, CLI, GUI).

**README:** [publishing](../pipeline/publishing/README.md)

---

## Planned cross-flow stages (Wave 5–7)

| Stage id | Ticket | Notes |
|----------|--------|-------|
| `elevenlabs_prompt_craft` | BUILD-064 | OpenAI crafts prompts per `asset_id` before REST generate |
| `sound_design_vo_finalize` | BUILD-066 | Optional VO bridge cue adjustments |
| `_arbiter` | BUILD-073 | Meta-stage; not in operator UI — [llm-arbiter-contract.md](../prompts/_shared/llm-arbiter-contract.md) |

---

## Stage → documentation index

| Concern | Doc |
|---------|-----|
| LLM volley + tiers | [analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md) |
| Context per stage | [context-padding.md](../cross-cutting/context-padding.md) |
| Artifacts paths | [artifact-layout.md](../cross-cutting/artifact-layout.md) |
| JSON schemas | [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md) |
| Operator verification | [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) |
| GUI panels | [gui-surface-map.md](../workflows/gui-surface-map.md) |

---

## Drift watchlist

Update this table when closing gaps:

| Item | Code | Docs / GUI |
|------|------|------------|
| Flow 3 stages | Not in `pipeline.py` | Listed in G2 copy, publishing README |
| G2 API | `flow1\|flow2` regex | Operator docs mention flow3 |
| `web/stages.py` | No `FLOW3_STAGES` | gui-surface-map has Flow 3 placeholders |
| v1 mux | Speech-only | assembly README describes target mix |

See [repository-map.md](./repository-map.md#known-doc--code-gaps-track-in-steps-forwardmd).
