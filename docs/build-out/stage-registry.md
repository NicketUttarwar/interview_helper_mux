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
| `audio_preclean` | shipped | `stages/audio_preclean.py` | BUILD-019 | `preclean/isolated.wav`, `preclean/lineage.json`, `vo_pickup/clean/` | — · [audio_preclean/README.md](../pipeline/audio_preclean/README.md) |

---

## Shared analysis

**Default order (`ANALYSIS_ORDER`):** `audio_preclean` → `ingest` → `transcribe` → `transcript_review_build` → `source_acoustic_profile` → `speaker_roles` → `content_context` → `boundary_detection` → `segment_classification` → `sound_design_palettes` → `missing_framing` → `optimal_questions`

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
| `sound_design_plan_init` | shipped (init hook) | `analysis_memory.py` | BUILD-060 | `understanding/sound_design_plan.json` (empty scaffold) | `cross-cutting/json-schemas/sound_design_plan.schema.json` |
| `source_acoustic_profile` | shipped | `understanding.py` | BUILD-082 | `understanding/source_acoustic_profile.json` | deterministic derivation · [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) |
| `sound_design_palettes` | shipped | `sound_design_stages.py` | BUILD-061 | SDP `palettes`, `coherence` | `sound_design/theme-palettes` |

**GUI-only (not in `ANALYSIS_ORDER`):** `analysis_profile` — edit `analysis_state.json` ([analysis-memory.md](../cross-cutting/analysis-memory.md)).

**Pipeline README:** [capture](../pipeline/capture/README.md) · [ingest](../pipeline/ingest/README.md) · [transcription](../pipeline/transcription/README.md) · [understanding](../pipeline/understanding/README.md) · [segmentation](../pipeline/segmentation/README.md) · [interviewer-gap](../pipeline/interviewer-gap/README.md)

---

## Gates

| Gate id | Status | Module | Ticket | Sets / checks | Doc |
|---------|--------|--------|--------|---------------|-----|
| G0 `transcript_review` | shipped | `gates.py`, `transcript_review.py` | BUILD-017 | STT corrections before `speaker_roles` | [operator-gates.md](../workflows/operator-gates.md) |
| G1 `g1_vo_pickup` | shipped | `gates.py`, `gaps.py` | BUILD-017 | `vo_pickup/` for `delivery: record` | same |
| G2 `g2_flow_select` | shipped | `gates.py`, `server.py` | BUILD-017, **080** | `run_meta.selected_flow` — API: flow1 \| flow2 \| flow3 | same |

---

## Flow 1 — full master podcast

**Default order (`FLOW1_ORDER` in `pipeline.py`):** `topic_coverage_audit` → `narrative_arc_plan` → `full_master_ranking` → `transitions` → `sound_design_plan_flow1` → `edl_flow1` → `assembly_preview` → `elevenlabs_prompt_craft` → `elevenlabs_sfx_flow1` → `mix_flow1` → `master_flow1`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `topic_coverage_audit` | shipped | `analysis_flow1_extended.py` | BUILD-029 | `flow_1_master/coverage_audit.json` | `selection/topic-coverage-audit` |
| `narrative_arc_plan` | shipped | `analysis_flow1_extended.py` | BUILD-030 | `flow_1_master/narrative_plan.json` | `selection/narrative-arc-plan` |
| `full_master_ranking` | shipped | `selection_flow1.py` | BUILD-031 | `flow_1_master/selection.json` | `selection/full-master-ranking` |
| `transitions` | shipped | `selection_flow1.py` | BUILD-032 | `flow_1_master/transitions.json` | `assembly/transitions` |
| `sound_design_plan_flow1` | shipped | `sound_design_stages.py` | BUILD-062 | SDP `assets` + `flow_plans.flow1.cues` | `sound_design/plan-flow1` |
| `edl_flow1` | shipped | `assembly_flow1.py` | BUILD-035, **067** | `flow_1_master/edl.json` — speech + `vo_pickup` + transition events | — |
| `assembly_preview` | shipped | `assembly_flow1.py` | BUILD-069 | `flow_1_master/assembly_preview.wav` (speech + VO, no SFX) | — |
| `elevenlabs_prompt_craft` | shipped | `sound_design_stages.py` | BUILD-064 | `sound_design/elevenlabs_prompts.json` | craft per `asset_id` |
| `elevenlabs_sfx_flow1` | shipped | `sfx_elevenlabs.py` | BUILD-034, **064** | `sound_design/assets/*.wav` (+ legacy `flow_1_master/sfx/`) | REST generate |
| `mix_flow1` | shipped | `assembly_flow1.py` → `sound_design.mix_flow1` | BUILD-035, **065**, **066**, 067 | `flow_1_master/assembly.wav` — speech + VO + SDP overlays | — |
| `master_flow1` | shipped | `mastering.py` | BUILD-036, **071** | `flow_1_master/master.wav` | — |
| `podcast_sfx_brief` | shipped (v1 legacy) | `selection_flow1.py` | BUILD-033 | `flow_1_master/podcast_sfx_brief.json` | `assembly/podcast-sfx-brief` — **not in `FLOW1_ORDER`** |
| `mux_flow1` | shipped (legacy alias) | `assembly_flow1.run_mux` | BUILD-066 | Same as `mix_flow1`; single-stage rerun only | — |

**Narrative QC (config-driven):** `narrative_qc.py` warns or blocks (when `narrative_qc.strict: true`) before `full_master_ranking` and `edl_flow1`. CLI: `tools/validate_narrative.py`.

**README:** [scoring_and_selection](../pipeline/scoring_and_selection/README.md) · [audio_editing](../pipeline/audio_editing/README.md) · [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [mastering_and_export](../pipeline/mastering_and_export/README.md)

---

## Flow 2 — highlight reel

**Default order (`FLOW2_ORDER`):** `highlight_selection` → `sound_design_plan_flow2` → `elevenlabs_prompt_craft` → `elevenlabs_sfx_flow2` → `mix_flow2` → `master_flow2`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `highlight_selection` | shipped | `selection_flow2.py` | BUILD-040 | `flow_2_highlights/selection.json` | `selection/highlight-selection` |
| `sound_design_plan_flow2` | shipped | `sound_design_stages.py` | BUILD-063 | SDP `assets` + `flow_plans.flow2.cues` | `sound_design/plan-flow2` |
| `elevenlabs_prompt_craft` | shipped | `sound_design_stages.py` | BUILD-064 | `sound_design/elevenlabs_prompts.json` | craft per `asset_id` |
| `elevenlabs_sfx_flow2` | shipped | `sfx_elevenlabs.py` | BUILD-042, **064** | `sound_design/assets/*.wav` (+ legacy `flow_2_highlights/sfx/`) | REST generate |
| `mix_flow2` | shipped | `assembly_flow2.py` → `sound_design.mix_flow2` | BUILD-043, **065**, **066** | `flow_2_highlights/assembly.wav` — montage + SDP transitions | — |
| `master_flow2` | shipped | `mastering.py` | BUILD-044 | `flow_2_highlights/master.wav` | — |
| `sfx_brief` | shipped (v1 legacy) | `selection_flow2.py` | BUILD-041 | `flow_2_highlights/sfx_brief.json` | `assembly/sfx-brief` — **not in `FLOW2_ORDER`** |
| `mux_flow2` | shipped (legacy alias) | `assembly_flow2.run_micro_assembly` | BUILD-066 | Same as `mix_flow2`; single-stage rerun only | — |

---

## Flow 3 — publishing copy

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `podcast_show_description` | shipped | `publishing_flow3.py` | BUILD-045 | `flow_3_description/show_description.json` | `publishing/podcast-show-description` |
| `export_show_description` | shipped | `publishing_flow3.py` | BUILD-046 | `flow_3_description/show_description.md` | — |

**Shipped (BUILD-080):** `FLOW3_ORDER`, `run_flow3`, CLI/GUI `flow3` mode.

**README:** [publishing](../pipeline/publishing/README.md)

---

## Optional cross-flow stages (Wave 5–7)

| Stage id | Status | Ticket | Notes |
|----------|--------|--------|-------|
| `sound_design_vo_finalize` | shipped | BUILD-066 / gap-closure | VO bridge cue duration finalize from vo_pickup WAVs |
| `_arbiter` | shipped (meta) | BUILD-073 | Meta-stage; not in operator UI — [llm-arbiter-contract.md](../prompts/_shared/llm-arbiter-contract.md) |

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
| EDL schema validator | `validate_edl_flow1` in `edl_flow1` + `tools/verify_edl.py` | Wired (BUILD-067) |
| Narrative QC | `narrative_qc.py` + `tools/validate_narrative.py` | Wired; `narrative_qc.strict` in config |
| Value analysis auto-extract | `value_analysis/extract.py` | Opt-in via `value_analysis.auto_extract_after_content_context` |

See [repository-map.md](./repository-map.md#known-doc--code-gaps-track-in-steps-forwardmd).
