# Stage registry

Authoritative list of **every pipeline stage** (shipped, gate, and planned). When adding a stage, update this file, `pipeline.py`, `web/stages.py`, the matching `docs/pipeline/*/README.md`, and [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) in the same PR.

**Code source of truth (shipped orders):** `src/interview_mux/pipeline.py` — `ANALYSIS_ORDER` (line ~52), `DELIVERY_ORDER` (~69), `REMOVED_FLOW2_ORDER` (~85), `REMOVED_FLOW3_ORDER` (~94).

---

## Legend

| Status | Meaning |
|--------|---------|
| **shipped** | In `pipeline.py` and runnable |
| **gate** | Operator checkpoint; may not use `.stage_done` |
| **planned** | Spec + ticket; not in `pipeline.py` yet |

**GUI substeps:** Each stage’s operator actions appear as **substeps** under that stage in the Pipeline Steps sidebar. Sources: `stages[].guidance` items (`prerequisites` + `actions`, stable `id`) and runtime attention (write approval, handoff, reuse). Gate stages use `kind: checkpoint` with optional `substep_label` for shorter sidebar text. Mapping: [gui-surface-map.md](../workflows/gui-surface-map.md).

**GUI sidebar order (`operator_stages_for_run`):** Linear operator progression — gates are interleaved where they block (e.g. `transcript_review_build` → **G0** → `disfluency_extract` → **G0.5** → `source_acoustic_profile` → … → **profile** → **G1** → **G2** → flow stages). Automated batch order remains `ANALYSIS_ORDER` in `pipeline.py`.

---

## Optional — pre-analysis

| Stage id | Status | Module | Ticket | Primary outputs | Prompt / spec |
|----------|--------|--------|--------|-----------------|---------------|
| `audio_preclean` | shipped | `stages/audio_preclean.py` | BUILD-019 | `preclean/isolated.wav`, `preclean/lineage.json`, `vo_pickup/clean/` | — · [audio_preclean/README.md](../pipeline/audio_preclean/README.md) |

---

## Shared analysis

**Default order (`ANALYSIS_ORDER`):** `audio_preclean` → `ingest` → `transcribe` → `transcript_review_build` → `disfluency_extract` → `source_acoustic_profile` → `interview_spine_build` → `speaker_roles` → ... → `content_brief_reanchor` → `sonic_context_build` → `sound_design_palettes` → `missing_framing` → `optimal_questions` → `delivery_brief_build`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `ingest` | shipped | `ingest.py` | BUILD-020 | `ingest/normalized.wav`, `ingest/checksums.json` | — |
| `transcribe` | shipped | `transcribe_aws.py` | BUILD-021 | `transcript/full.json`, `transcript/speakers.json` | — |
| `transcript_review_build` | shipped | `transcript_review.py` | BUILD-018 | `transcript/review_queue.json` | — |
| `disfluency_extract` | shipped | `disfluency.py` | — | `transcript/disfluencies.json`, `transcript/disfluency_clips/` | Gate `disfluency_review` (G0.5) |
| `transcript_review` | gate | `transcript_review.py` | BUILD-018 | `transcript/corrections.json`; dock: `patch_transcript_words` → `transcript/full.json` | GUI: `TranscriptDockViewer`, `FuzzyReplacePopover` |
| `speaker_roles` | shipped | `understanding.py` | BUILD-022 | `understanding/speakers.json` | `understanding/speaker-roles` |
| `source_topology_build` | shipped | `source_topology.py` | TBIY | `understanding/source_topology.json`, `understanding/flow_adaptation.json` | deterministic · [tbiy-production-profile.md](../cross-cutting/tbiy-production-profile.md) |
| `content_context` | shipped | `understanding.py` | BUILD-023 | `understanding/content_brief.json` | `understanding/content-context` (+ `.tbiy` variant) |
| `boundary_detection` | shipped | `segmentation.py` | BUILD-024 | `segments/boundaries.json` | `segmentation/boundary-detection` |
| `segment_classification` | shipped | `segmentation.py` | BUILD-024 | `segments/manifest.json` | `segmentation/segment-classification` |
| `content_brief_reanchor` | shipped | `understanding.py` | BUILD-023 | `understanding/content_brief.json` (patch) | `understanding/content-brief-reanchor` |
| `sonic_context_build` | shipped | `stages/sonic_context_stages.py` | BUILD-SFX-01 | `understanding/sonic_context.json` | deterministic build from brief/profile/segments |
| `missing_framing` | shipped | `gaps.py` | BUILD-025 | `understanding/gap_evaluations.json` | `interviewer-gap/missing-framing` |
| `optimal_questions` | shipped | `gaps.py` | BUILD-026 | `understanding/gap_report.json`, `interviewer_script.txt` | `interviewer-gap/optimal-questions` |
| `delivery_brief_build` | shipped | `delivery_brief.py` | adaptive policy | `understanding/delivery_brief.json` | [delivery-quality-preservation-matrix.md](../cross-cutting/delivery-quality-preservation-matrix.md) |

**First-try:** after ingest, also writes `understanding/source_readiness.json` (see [first-try-reliability.md](../workflows/first-try-reliability.md)).
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
| G2 `REMOVED_g2_flow_select` | shipped | `gates.py`, `server.py` | BUILD-017, **080** | `run_meta.REMOVED_selected_flow` — API: flow1 \| flow2 \| flow3 | same |

---

## Flow 1 — full master podcast

**Default order (`DELIVERY_ORDER` in `pipeline.py`):** `topic_coverage_audit` → `narrative_arc_plan` → `full_master_ranking` → `transitions` → `sound_design_plan` → `sound_design_vo_finalize` → `edl_narrative_audit` → `edl` → `assembly_preview` → `sfx_prompt_craft` → `mmaudio_sfx` → `mix` → `master_finalize`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `topic_coverage_audit` | shipped | `analysis_extended.py` | BUILD-029 | `master/coverage_audit.json` | `selection/topic-coverage-audit` |
| `narrative_arc_plan` | shipped | `analysis_extended.py` | BUILD-030 | `master/narrative_plan.json` | `selection/narrative-arc-plan` |
| `full_master_ranking` | shipped | `selection.py` | BUILD-031 | `master/selection.json` | `selection/full-master-ranking` |
| `transitions` | shipped | `selection.py` | BUILD-032 | `master/transitions.json` | `assembly/transitions` |
| `sound_design_plan` | shipped | `sound_design_stages.py` | BUILD-062 | SDP `assets` + `flow_plans.podcast.cues` | `sound_design/plan-flow1` |
| `sound_design_vo_finalize` | shipped | `sound_design_vo_finalize.py` | BUILD-066 / gap-closure | SDP `flow_plans.podcast.cues[]` — `measured_duration_ms` from `vo_pickup/` WAVs | — |
| `edl_narrative_audit` | shipped | `edl_narrative_audit.py` | EDL narrative QC | `master/edl_narrative_audit.json` | `selection/edl-narrative-audit` |
| `edl` | shipped | `assembly.py` | BUILD-035, **067** | `master/edl.json` — speech + `vo_pickup` + transition events | — |
| `assembly_preview` | shipped | `assembly.py` | BUILD-069 | `master/assembly_preview.wav` (speech + VO, no SFX) | — |
| `sfx_prompt_craft` | shipped | `sound_design_stages.py` | BUILD-064 | `sound_design/sfx_prompts.json` | craft per `asset_id` |
| `sfx_prompt_refine` | shipped (optional) | `sound_design_stages.py` | MMAudio stack | updated `sfx_prompts.json` | `sound_design/sfx-prompt-refine` — **not in default FLOW order**; API `POST …/sfx-prompts/refine` or `auto_refine_enabled` |
| `mmaudio_sfx` | shipped | `sfx_mmaudio.py` | BUILD-034, **064** | `sound_design/assets/*.wav` (+ legacy `master/sfx/`) | local MMAudio generate |
| `mix` | shipped | `assembly.py` → `sound_design.mix` | BUILD-035, **065**, **066**, 067 | `master/assembly.wav` — speech + VO + SDP overlays | — |
| `master_finalize` | shipped | `mastering.py` | BUILD-036, **071** | `master/master.wav` | — |
| `podcast_sfx_brief` | shipped (v1 legacy) | `selection.py` | BUILD-033 | `master/podcast_sfx_brief.json` | `assembly/podcast-sfx-brief` — **not in `DELIVERY_ORDER`** |
| `mux_flow1` | shipped (legacy alias) | `assembly.run_mux` | BUILD-066 | Same as `mix`; single-stage rerun only | — |

**Narrative QC (config-driven):** `narrative_qc.py` warns or blocks (when `narrative_qc.strict: true`) before `full_master_ranking` and `edl`. `edl_narrative_qc.py` validates final EDL narrative semantics before `edl.json` is written (`edl_narrative_qc.strict`). CLI: `tools/validate_narrative.py --include-edl`.

**README:** [scoring_and_selection](../pipeline/scoring_and_selection/README.md) · [audio_editing](../pipeline/audio_editing/README.md) · [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [mastering_and_export](../pipeline/mastering_and_export/README.md)

---

## Flow 2 — highlight reel

**Default order (`REMOVED_FLOW2_ORDER`):** `REMOVED_highlight_selection` → `REMOVED_sdp_flow2` → `sfx_prompt_craft` → `REMOVED_mmaudio_flow2` → `REMOVED_mix_flow2` → `REMOVED_master_flow2`

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `REMOVED_highlight_selection` | shipped | `REMOVED_selection_flow2.py` | BUILD-040 | `REMOVED_flow2/selection.json` | `selection/highlight-selection` |
| `REMOVED_sdp_flow2` | shipped | `sound_design_stages.py` | BUILD-063 | SDP `assets` + `REMOVED_flow_plans_flow2.cues` | `sound_design/plan-flow2` |
| `sfx_prompt_craft` | shipped | `sound_design_stages.py` | BUILD-064 | `sound_design/sfx_prompts.json` | craft per `asset_id` |
| `sfx_prompt_refine` | shipped (optional) | `sound_design_stages.py` | MMAudio stack | updated `sfx_prompts.json` | `sound_design/sfx-prompt-refine` — **not in default FLOW order** |
| `REMOVED_mmaudio_flow2` | shipped | `sfx_mmaudio.py` | BUILD-042, **064** | `sound_design/assets/*.wav` (+ legacy `REMOVED_flow2/sfx/`) | local MMAudio generate |
| `REMOVED_mix_flow2` | shipped | `REMOVED_assembly_flow2.py` → `sound_design.REMOVED_mix_flow2` | BUILD-043, **065**, **066** | `REMOVED_flow2/assembly.wav` — montage + SDP transitions | — |
| `REMOVED_master_flow2` | shipped | `mastering.py` | BUILD-044 | `REMOVED_flow2/master.wav` | — |
| `sfx_brief` | shipped (v1 legacy) | `REMOVED_selection_flow2.py` | BUILD-041 | `REMOVED_flow2/sfx_brief.json` | `assembly/sfx-brief` — **not in `REMOVED_FLOW2_ORDER`** |
| `mux_flow2` | shipped (legacy alias) | `REMOVED_assembly_flow2.run_micro_assembly` | BUILD-066 | Same as `REMOVED_mix_flow2`; single-stage rerun only | — |

---

## Flow 3 — publishing copy

**Default order (`REMOVED_FLOW3_ORDER` in `pipeline.py`):** `REMOVED_podcast_show_description` → `REMOVED_export_show_description`

**Analysis-only prerequisites:** `REMOVED_run_flow3` calls `require_g1_clear` + `require_analysis_artifacts_complete` (cross-artifact validation + profile ready). Does **not** require Flow 1 ranking or Flow 2 selection. LLM preflight for `REMOVED_podcast_show_description` when `REMOVED_selected_flow: flow3` checks `understanding/content_brief.json`, `understanding/speakers.json`, `segments/manifest.json`.

| Stage id | Status | Module | Ticket | Primary outputs | Prompt |
|----------|--------|--------|--------|-----------------|--------|
| `REMOVED_podcast_show_description` | shipped | `REMOVED_publishing_flow3.py` | BUILD-045 | `show_notes/show_description.json` | `publishing/podcast-show-description` |
| `REMOVED_export_show_description` | shipped | `REMOVED_publishing_flow3.py` | BUILD-046 | `show_notes/show_description.md` | — |

**Shipped (BUILD-080):** `REMOVED_FLOW3_ORDER`, `REMOVED_run_flow3`, CLI/GUI `flow3` mode.

**README:** [publishing](../pipeline/publishing/README.md)

---

## Optional cross-flow stages (Wave 5–7)

| Stage id | Status | Ticket | Notes |
|----------|--------|--------|-------|
| `sound_design_vo_finalize` | shipped (in `DELIVERY_ORDER`) | BUILD-066 / gap-closure | VO bridge cue duration finalize from vo_pickup WAVs — see Flow 1 table above |
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
| EDL schema validator | `validate_edl` in `edl` + `tools/verify_edl.py` | Wired (BUILD-067) |
| Narrative QC | `narrative_qc.py`, `edl_narrative_qc.py` + `tools/validate_narrative.py --include-edl` | Wired; `narrative_qc.strict` and `edl_narrative_qc.strict` in config |
| Value analysis auto-extract | `value_analysis/extract.py` | Opt-in via `value_analysis.auto_extract_after_content_context` |

See [repository-map.md](./repository-map.md#known-doc--code-gaps-track-in-steps-forwardmd).
