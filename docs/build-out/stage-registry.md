# Stage registry

Authoritative list of **every pipeline stage** (shipped, gate, and planned). When adding a stage, update this file, `pipeline.py`, `web/stages.py`, the matching `docs/pipeline/*/README.md`, and [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) in the same PR.

**Code source of truth (shipped orders):** `src/interview_mux/pipeline.py` — `ANALYSIS_ORDER` (line ~52), `FLOW1_ORDER` (~69), `FLOW2_ORDER` (~85), `FLOW3_ORDER` (~94).

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

**Default order (`ANALYSIS_ORDER`):** `audio_preclean` → `ingest` → `transcribe` → `transcript_review_build` → `disfluency_extract` → `source_acoustic_profile` → `interview_spine_build` → `speaker_roles` → ... → `content_brief_reanchor` → `sonic_context_build` → `sound_design_palettes` → `missing_framing` → `optimal_questions`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `ingest` | shipped | `ingest.py` | BUILD-020 | `ingest/normalized.wav`, `ingest/checksums.json` | — |
| `transcribe` | shipped | `transcribe_aws.py` | BUILD-021 | `transcript/full.json`, `transcript/speakers.json` | — |
| `transcript_review_build` | shipped | `transcript_review.py` | BUILD-018 | `transcript/review_queue.json` | — |
| `disfluency_extract` | shipped | `disfluency.py` | — | `transcript/disfluencies.json`, `transcript/disfluency_clips/` | Gate `disfluency_review` (G0.5) |
| `transcript_review` | gate | `transcript_review.py` | BUILD-018 | `transcript/corrections.json`; dock: `patch_transcript_words` → `transcript/full.json` | GUI: `TranscriptDockViewer`, `FuzzyReplacePopover` |
| `speaker_roles` | shipped | `understanding.py` | BUILD-022 | `understanding/speakers.json` | `understanding/speaker-roles` |
| `content_context` | shipped | `understanding.py` | BUILD-023 | `understanding/content_brief.json` | `understanding/content-context` |
| `boundary_detection` | shipped | `segmentation.py` | BUILD-024 | `segments/boundaries.json` | `segmentation/boundary-detection` |
| `segment_classification` | shipped | `segmentation.py` | BUILD-024 | `segments/manifest.json` | `segmentation/segment-classification` |
| `content_brief_reanchor` | shipped | `understanding.py` | BUILD-023 | `understanding/content_brief.json` (patch) | `understanding/content-brief-reanchor` |
| `sonic_context_build` | shipped | `stages/sonic_context_stages.py` | BUILD-SFX-01 | `understanding/sonic_context.json` | deterministic build from brief/profile/segments |
| `missing_framing` | shipped | `gaps.py` | BUILD-025 | `understanding/gap_evaluations.json` | `interviewer-gap/missing-framing` |
| `optimal_questions` | shipped | `gaps.py` | BUILD-026 | `understanding/gap_report.json`, `interviewer_script.txt` | `interviewer-gap/optimal-questions` |
| `vo_ingest` | shipped (on-demand) | `gaps.py` | BUILD-027 | Merges `vo_pickup/*.wav` into timeline; **not in `ANALYSIS_ORDER`** — triggered by next batch execute after G1 or `mode: stage` | — |
| `sound_design_plan_init` | shipped (init hook) | `analysis_memory.py` | BUILD-060 | `understanding/sound_design_plan.json` (empty scaffold) | `cross-cutting/json-schemas/sound_design_plan.schema.json` |
| `source_acoustic_profile` | shipped | `understanding.py` | BUILD-082 | `understanding/source_acoustic_profile.json` | deterministic derivation · [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) |
| `interview_spine_build` | shipped | `interview_spine_stage.py` | BUILD-083 | `understanding/interview_spine.json` (+ optional `embeddings.npz`) | H-ORC-01 local comprehension index · [interview-spine.md](../cross-cutting/interview-spine.md) |
| Coherence hooks (H-ORC-03) | shipped | `coherence/analyze.py` | — | `understanding/coherence_report.json` | After `content_context` / `content_brief_reanchor` / `topic_coverage_audit` · [coherence-orc03.md](../cross-cutting/coherence-orc03.md) |
| `sound_design_palettes` | shipped | `sound_design_stages.py` | BUILD-061 | SDP `palettes`, `coherence` | `sound_design/theme-palettes` |

**GUI-only (not in `ANALYSIS_ORDER`):** `analysis_profile` — edit `analysis_state.json` ([analysis-memory.md](../cross-cutting/analysis-memory.md)).

**Pipeline README:** [capture](../pipeline/capture/README.md) · [ingest](../pipeline/ingest/README.md) · [transcription](../pipeline/transcription/README.md) · [understanding](../pipeline/understanding/README.md) · [segmentation](../pipeline/segmentation/README.md) · [interviewer-gap](../pipeline/interviewer-gap/README.md)

---

## Gates

| Gate id | Status | Module | Ticket | Sets / checks | Doc |
|---------|--------|--------|--------|---------------|-----|
| G0 `transcript_review` | shipped | `gates.py`, `transcript_review.py` | BUILD-017 | STT corrections before `speaker_roles` | [operator-gates.md](../workflows/operator-gates.md) |
| G0.5 `disfluency_review` | shipped | `gates.py`, `disfluency.py` | — | Filler catalog sign-off after `disfluency_extract`; auto-skipped when extract disabled | [disfluency-extract.md](../pipeline/transcription/disfluency-extract.md) |
| G1 `g1_vo_pickup` | shipped | `gates.py`, `gaps.py` | BUILD-017 | `vo_pickup/` for `delivery: record` | same |
| G2 `g2_flow_select` | shipped | `gates.py`, `server.py` | BUILD-017, **080** | `run_meta.selected_flow` — API: flow1 \| flow2 \| flow3 | same |

---

## Flow 1 — full master podcast

**Default order (`FLOW1_ORDER` in `pipeline.py`):** `topic_coverage_audit` → `narrative_arc_plan` → `full_master_ranking` → `transitions` → `sound_design_plan_flow1` → `sound_design_vo_finalize` → `edl_narrative_audit` → `edl_flow1` → `assembly_preview` → `sfx_prompt_craft` → `mmaudio_sfx_flow1` → `mix_flow1` → `master_flow1`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `topic_coverage_audit` | shipped | `analysis_flow1_extended.py` | BUILD-029 | `flow_1_master/coverage_audit.json` | `selection/topic-coverage-audit` |
| `narrative_arc_plan` | shipped | `analysis_flow1_extended.py` | BUILD-030 | `flow_1_master/narrative_plan.json` | `selection/narrative-arc-plan` |
| `full_master_ranking` | shipped | `selection_flow1.py` | BUILD-031 | `flow_1_master/selection.json` | `selection/full-master-ranking` |
| `transitions` | shipped | `selection_flow1.py` | BUILD-032 | `flow_1_master/transitions.json` | `assembly/transitions` |
| `sound_design_plan_flow1` | shipped | `sound_design_stages.py` | BUILD-062 | SDP `assets` + `flow_plans.flow1.cues` | `sound_design/plan-flow1` |
| `sound_design_vo_finalize` | shipped | `sound_design_vo_finalize.py` | BUILD-066 / gap-closure | SDP `flow_plans.flow1.cues[]` — `measured_duration_ms` from `vo_pickup/` WAVs | — |
| `edl_narrative_audit` | shipped | `edl_narrative_audit.py` | EDL narrative QC | `flow_1_master/edl_narrative_audit.json` | `selection/edl-narrative-audit` |
| `edl_flow1` | shipped | `assembly_flow1.py` | BUILD-035, **067** | `flow_1_master/edl.json` — speech + `vo_pickup` + transition events | — |
| `assembly_preview` | shipped | `assembly_flow1.py` | BUILD-069 | `flow_1_master/assembly_preview.wav` (speech + VO, no SFX) | — |
| `sfx_prompt_craft` | shipped | `sound_design_stages.py` | BUILD-064 | `sound_design/sfx_prompts.json` | craft per `asset_id` |
| `sfx_prompt_refine` | shipped (optional) | `sound_design_stages.py` | MMAudio stack | updated `sfx_prompts.json` | `sound_design/sfx-prompt-refine` — **not in default FLOW order**; API `POST …/sfx-prompts/refine` or `auto_refine_enabled` |
| `mmaudio_sfx_flow1` | shipped | `sfx_mmaudio.py` | BUILD-034, **064** | `sound_design/assets/*.wav` (+ legacy `flow_1_master/sfx/`) | local MMAudio generate |
| `mix_flow1` | shipped | `assembly_flow1.py` → `sound_design.mix_flow1` | BUILD-035, **065**, **066**, 067 | `flow_1_master/assembly.wav` — speech + VO + SDP overlays | — |
| `master_flow1` | shipped | `mastering.py` | BUILD-036, **071** | `flow_1_master/master.wav` | — |
| `podcast_sfx_brief` | shipped (v1 legacy) | `selection_flow1.py` | BUILD-033 | `flow_1_master/podcast_sfx_brief.json` | `assembly/podcast-sfx-brief` — **not in `FLOW1_ORDER`** |
| `mux_flow1` | shipped (legacy alias) | `assembly_flow1.run_mux` | BUILD-066 | Same as `mix_flow1`; single-stage rerun only | — |

**Narrative QC (config-driven):** `narrative_qc.py` warns or blocks (when `narrative_qc.strict: true`) before `full_master_ranking` and `edl_flow1`. `edl_narrative_qc.py` validates final EDL narrative semantics before `edl.json` is written (`edl_narrative_qc.strict`). CLI: `tools/validate_narrative.py --include-edl`.

**README:** [scoring_and_selection](../pipeline/scoring_and_selection/README.md) · [audio_editing](../pipeline/audio_editing/README.md) · [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [mastering_and_export](../pipeline/mastering_and_export/README.md)

---

## Flow 2 — highlight reel

**Default order (`FLOW2_ORDER`):** `highlight_selection` → `sound_design_plan_flow2` → `sfx_prompt_craft` → `mmaudio_sfx_flow2` → `mix_flow2` → `master_flow2`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `highlight_selection` | shipped | `selection_flow2.py` | BUILD-040 | `flow_2_highlights/selection.json` | `selection/highlight-selection` |
| `sound_design_plan_flow2` | shipped | `sound_design_stages.py` | BUILD-063 | SDP `assets` + `flow_plans.flow2.cues` | `sound_design/plan-flow2` |
| `sfx_prompt_craft` | shipped | `sound_design_stages.py` | BUILD-064 | `sound_design/sfx_prompts.json` | craft per `asset_id` |
| `sfx_prompt_refine` | shipped (optional) | `sound_design_stages.py` | MMAudio stack | updated `sfx_prompts.json` | `sound_design/sfx-prompt-refine` — **not in default FLOW order** |
| `mmaudio_sfx_flow2` | shipped | `sfx_mmaudio.py` | BUILD-042, **064** | `sound_design/assets/*.wav` (+ legacy `flow_2_highlights/sfx/`) | local MMAudio generate |
| `mix_flow2` | shipped | `assembly_flow2.py` → `sound_design.mix_flow2` | BUILD-043, **065**, **066** | `flow_2_highlights/assembly.wav` — montage + SDP transitions | — |
| `master_flow2` | shipped | `mastering.py` | BUILD-044 | `flow_2_highlights/master.wav` | — |
| `sfx_brief` | shipped (v1 legacy) | `selection_flow2.py` | BUILD-041 | `flow_2_highlights/sfx_brief.json` | `assembly/sfx-brief` — **not in `FLOW2_ORDER`** |
| `mux_flow2` | shipped (legacy alias) | `assembly_flow2.run_micro_assembly` | BUILD-066 | Same as `mix_flow2`; single-stage rerun only | — |

---

## Flow 3 — publishing copy

**Default order (`FLOW3_ORDER` in `pipeline.py`):** `podcast_show_description` → `export_show_description`

**Analysis-only prerequisites:** `run_flow3` calls `require_g1_clear` + `require_analysis_artifacts_complete` (cross-artifact validation + profile ready). Does **not** require Flow 1 ranking or Flow 2 selection. LLM preflight for `podcast_show_description` when `selected_flow: flow3` checks `understanding/content_brief.json`, `understanding/speakers.json`, `segments/manifest.json`.

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
| `sound_design_vo_finalize` | shipped (in `FLOW1_ORDER`) | BUILD-066 / gap-closure | VO bridge cue duration finalize from vo_pickup WAVs — see Flow 1 table above |
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

## Cross-run reuse

Before each automated stage runs, `stage_execution_reuse.resolve_before_stage_run` may pause for operator choice when a prior execution (same source audio) already completed that stage. See [stage-execution-reuse.md](../workflows/stage-execution-reuse.md).

---

## Drift watchlist

Update this table when closing gaps:

| Item | Code | Docs / GUI |
|------|------|------------|
| EDL schema validator | `validate_edl_flow1` in `edl_flow1` + `tools/verify_edl.py` | Wired (BUILD-067) |
| Narrative QC | `narrative_qc.py`, `edl_narrative_qc.py` + `tools/validate_narrative.py --include-edl` | Wired; `narrative_qc.strict` and `edl_narrative_qc.strict` in config |
| Value analysis auto-extract | `value_analysis/extract.py` | Opt-in via `value_analysis.auto_extract_after_content_context` |

See [repository-map.md](./repository-map.md#known-doc--code-gaps-track-in-steps-forwardmd).
