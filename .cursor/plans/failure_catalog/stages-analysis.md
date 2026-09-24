# Analysis stage vulnerable-junction cards

Brain **0.1.0**. HEAD only. Identify-only.

Call graphs resolved from `pipeline._analysis_stage_fns` (AST). Incompleteness = string hit in `stage_artifact_incompleteness` body.

### STG-audio_preclean — stage `audio_preclean`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_audio_preclean`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["audio_preclean"]` → `audio_preclean.run_audio_preclean` → artifact writers → `.stage_done/audio_preclean`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: local-ML — model-tool-calls.md
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Partial prepare-until-G0 defers preclean; later DeepFilter can shift checksums vs G0-locked STT
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `audio_preclean.run_audio_preclean`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `partial-prepare-order`
- Status: OPEN_RISK

### STG-audio_preclean-partial-prepare — Partial prepare-until-G0 interaction
- Surface: stage / mode
- Modes affected: Partial (primary)
- Brain: 0.1.0
- Call graph: `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0` → web/runner prepare order
- Why weak: operator may assume audio cleaned / STT stable; later preclean shifts checksums vs G0 lock
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `partial-prepare-order`
- Evidence: `automation_run.py` PARTIAL_AUTO_PREPARE_UNTIL_G0

### STG-ingest — stage `ingest`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_ingest`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["ingest"]` → `ingest.run_ingest` → artifact writers → `.stage_done/ingest`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Mostly deterministic copy/normalize; residual hollow-done if incompleteness absent
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L1 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `ingest.run_ingest`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-ingest-partial-prepare — Partial prepare-until-G0 interaction
- Surface: stage / mode
- Modes affected: Partial (primary)
- Brain: 0.1.0
- Call graph: `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0` → web/runner prepare order
- Why weak: operator may assume audio cleaned / STT stable; later preclean shifts checksums vs G0 lock
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `partial-prepare-order`
- Evidence: `automation_run.py` PARTIAL_AUTO_PREPARE_UNTIL_G0

### STG-transcribe — stage `transcribe`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_transcribe`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["transcribe"]` → `transcribe_local.run_transcribe` → artifact writers → `.stage_done/transcribe`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: local-ML — model-tool-calls.md
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: MLX STT/diarization isolated venv; fail → weak transcript feeding G0
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `transcribe_local.run_transcribe`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `local-ml-venvs`
- Status: OPEN_RISK

### STG-transcribe-partial-prepare — Partial prepare-until-G0 interaction
- Surface: stage / mode
- Modes affected: Partial (primary)
- Brain: 0.1.0
- Call graph: `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0` → web/runner prepare order
- Why weak: operator may assume audio cleaned / STT stable; later preclean shifts checksums vs G0 lock
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `partial-prepare-order`
- Evidence: `automation_run.py` PARTIAL_AUTO_PREPARE_UNTIL_G0

### STG-transcript_review_build — stage `transcript_review_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_transcript_review_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["transcript_review_build"]` → `transcript_review.run_transcript_review_build` → artifact writers → `.stage_done/transcript_review_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Feeds G0; Full-auto auto-G0 can lock weak STT
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `transcript_review.run_transcript_review_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `mode-gate-honesty`
- Status: OPEN_RISK

### STG-transcript_review_build-partial-prepare — Partial prepare-until-G0 interaction
- Surface: stage / mode
- Modes affected: Partial (primary)
- Brain: 0.1.0
- Call graph: `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0` → web/runner prepare order
- Why weak: operator may assume audio cleaned / STT stable; later preclean shifts checksums vs G0 lock
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `partial-prepare-order`
- Evidence: `automation_run.py` PARTIAL_AUTO_PREPARE_UNTIL_G0

### STG-audio_probe_build — stage `audio_probe_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_audio_probe_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["audio_probe_build"]` → `audio_probes.run_audio_probe_build` → artifact writers → `.stage_done/audio_probe_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Probe fallbacks can mark thin acoustic truth
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `audio_probes.run_audio_probe_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `audio-probe-fallback`
- Status: OPEN_RISK

### STG-audio_probe_build-partial-prepare — Partial prepare-until-G0 interaction
- Surface: stage / mode
- Modes affected: Partial (primary)
- Brain: 0.1.0
- Call graph: `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0` → web/runner prepare order
- Why weak: operator may assume audio cleaned / STT stable; later preclean shifts checksums vs G0 lock
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `partial-prepare-order`
- Evidence: `automation_run.py` PARTIAL_AUTO_PREPARE_UNTIL_G0

### STG-source_acoustic_profile — stage `source_acoustic_profile`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_source_acoustic_profile`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["source_acoustic_profile"]` → `understanding.run_source_acoustic_profile` → artifact writers → `.stage_done/source_acoustic_profile`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: LLM/profile hollow; no incompleteness branch
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `understanding.run_source_acoustic_profile`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-interview_spine_build — stage `interview_spine_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_interview_spine_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["interview_spine_build"]` → `interview_spine_stage.run_interview_spine_build` → artifact writers → `.stage_done/interview_spine_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Spine LLM without incompleteness → hollow seed
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_spine_stage.run_interview_spine_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-speaker_roles — stage `speaker_roles`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_speaker_roles`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["speaker_roles"]` → `understanding.run_speaker_roles` → artifact writers → `.stage_done/speaker_roles`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/speakers.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Role/tape mismatch poisons framing/VO seats
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `understanding.run_speaker_roles`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-source_topology_build — stage `source_topology_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_source_topology_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["source_topology_build"]` → `interview_mux.source_topology.run_source_topology_build` → artifact writers → `.stage_done/source_topology_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Topology gates G-Framing eligibility
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.source_topology.run_source_topology_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-content_context — stage `content_context`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_content_context`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["content_context"]` → `understanding.run_content_context` → artifact writers → `.stage_done/content_context`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/content_brief.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Shared brief multi-writer drift
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `understanding.run_content_context`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-talking_points_compose — stage `talking_points_compose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_talking_points_compose`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["talking_points_compose"]` → `understanding.run_talking_points_compose` → artifact writers → `.stage_done/talking_points_compose`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/talking_points.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Thin TP poison ranking
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `understanding.run_talking_points_compose`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-ideal_cuts_propose — stage `ideal_cuts_propose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_ideal_cuts_propose`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["ideal_cuts_propose"]` → `understanding.run_ideal_cuts_propose` → artifact writers → `.stage_done/ideal_cuts_propose`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/ideal_cuts.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Propose without materialize honesty
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `understanding.run_ideal_cuts_propose`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-ideal_cuts_materialize — stage `ideal_cuts_materialize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_ideal_cuts_materialize`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["ideal_cuts_materialize"]` → `interview_mux.ideal_cuts.run_ideal_cuts_materialize` → artifact writers → `.stage_done/ideal_cuts_materialize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `understanding/ideal_cuts_materialized.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Materialize vs propose drift
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.ideal_cuts.run_ideal_cuts_materialize`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-boundary_detection — stage `boundary_detection`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_boundary_detection`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["boundary_detection"]` → `segmentation.run_boundaries` → artifact writers → `.stage_done/boundary_detection`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `segments/boundaries.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Shared boundaries.json multi-writer / self-stale clear_from
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `segmentation.run_boundaries`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `invalidation-blast`
- Status: OPEN_RISK

### STG-segment_classification — stage `segment_classification`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_segment_classification`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["segment_classification"]` → `segmentation.run_classification` → artifact writers → `.stage_done/segment_classification`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `segments/manifest.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Classification hollow → wrong omit/keep
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `segmentation.run_classification`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-content_brief_reanchor — stage `content_brief_reanchor`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_content_brief_reanchor`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["content_brief_reanchor"]` → `understanding.run_content_brief_reanchor` → artifact writers → `.stage_done/content_brief_reanchor`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/content_brief.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Reanchor shared brief mid-pipeline
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `understanding.run_content_brief_reanchor`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `invalidation-blast`
- Status: OPEN_RISK

### STG-framing_posture_decide — stage `framing_posture_decide`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_framing_posture_decide`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["framing_posture_decide"]` → `interview_mux.stages.framing_posture_decide.run_framing_posture_decide` → artifact writers → `.stage_done/framing_posture_decide`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/framing_posture_decision.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Advisory posture ≠ sticky Yes/No; auto-Yes ignores
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.stages.framing_posture_decide.run_framing_posture_decide`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `g-framing-authority`
- Status: OPEN_RISK

### STG-boundary_topic_resplit — stage `boundary_topic_resplit`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_boundary_topic_resplit`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["boundary_topic_resplit"]` → `segmentation.run_boundary_topic_resplit` → artifact writers → `.stage_done/boundary_topic_resplit`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `segments/boundaries.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Resplit invalidates shared boundaries
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `segmentation.run_boundary_topic_resplit`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `invalidation-blast`
- Status: OPEN_RISK

### STG-vernacular_segment_sanitize — stage `vernacular_segment_sanitize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_vernacular_segment_sanitize`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["vernacular_segment_sanitize"]` → `audio_probes.run_vernacular_segment_sanitize` → artifact writers → `.stage_done/vernacular_segment_sanitize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Sanitize fail-open leaves vernacular debt
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `audio_probes.run_vernacular_segment_sanitize`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-low_conf_island_scan — stage `low_conf_island_scan`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_low_conf_island_scan`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["low_conf_island_scan"]` → `interview_mux.stages.low_conf_fuse_stages.run_low_conf_island_scan` → artifact writers → `.stage_done/low_conf_island_scan`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `analysis/low_conf_islands.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Island scan advisory vs hard omit
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.stages.low_conf_fuse_stages.run_low_conf_island_scan`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-connector_fuse_pass — stage `connector_fuse_pass`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_connector_fuse_pass`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["connector_fuse_pass"]` → `interview_mux.stages.low_conf_fuse_stages.run_connector_fuse_pass` → artifact writers → `.stage_done/connector_fuse_pass`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `analysis/connector_fuse_audit.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Fuse can invent connectors over thin tape
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.stages.low_conf_fuse_stages.run_connector_fuse_pass`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-sonic_context_build — stage `sonic_context_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_sonic_context_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["sonic_context_build"]` → `sonic_context_stages.run_sonic_context_build` → artifact writers → `.stage_done/sonic_context_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Sonic context thin → SDP/MusicGen wrong
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `sonic_context_stages.run_sonic_context_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-sound_design_palettes — stage `sound_design_palettes`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_sound_design_palettes`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["sound_design_palettes"]` → `sound_design_stages.run_sound_design_palettes` → artifact writers → `.stage_done/sound_design_palettes`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/sound_design_plan.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Palette LLM without incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `sound_design_stages.run_sound_design_palettes`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-mastering_research_routing — stage `mastering_research_routing`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_research_routing`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_research_routing"]` → `interview_mux.mastering_research.run_mastering_research_routing` → artifact writers → `.stage_done/mastering_research_routing`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `mastering/research/routing.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Existence probe soft-gate; router prompt unwired
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_research.run_mastering_research_routing`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-mastering_research_waves — stage `mastering_research_waves`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_research_waves`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_research_waves"]` → `interview_mux.mastering_research.run_mastering_research_waves` → artifact writers → `.stage_done/mastering_research_waves`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `mastering/research/waves.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Probes future delivery artifacts mid-analysis → permanent thin
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_research.run_mastering_research_waves`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-mastering_research_rollup — stage `mastering_research_rollup`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_research_rollup`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_research_rollup"]` → `interview_mux.mastering_research.run_mastering_research_rollup` → artifact writers → `.stage_done/mastering_research_rollup`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `mastering/research/rollup.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Re-probes all waves; duplicate no delta
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S1
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_research.run_mastering_research_rollup`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-mastering_shape_agenda — stage `mastering_shape_agenda`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_shape_agenda`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_shape_agenda"]` → `interview_mux.mastering_shape_runtime.run_mastering_shape_agenda` → artifact writers → `.stage_done/mastering_shape_agenda`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Heuristics not L0 meta-architect LLM
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_shape_runtime.run_mastering_shape_agenda`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-mastering_shape_candidates — stage `mastering_shape_candidates`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_shape_candidates`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_shape_candidates"]` → `interview_mux.mastering_shape_runtime.run_mastering_shape_candidates` → artifact writers → `.stage_done/mastering_shape_candidates`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Fake ordinal scores; no L1–L2
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_shape_runtime.run_mastering_shape_candidates`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-mastering_plan_synthesize — stage `mastering_plan_synthesize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_plan_synthesize`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_plan_synthesize"]` → `interview_mux.mastering_shape_runtime.run_mastering_plan_synthesize` → artifact writers → `.stage_done/mastering_plan_synthesize`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Picks candidates[0]; flagship synthesize unwired
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_shape_runtime.run_mastering_plan_synthesize`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-missing_framing — stage `missing_framing`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_missing_framing`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["missing_framing"]` → `_run_missing_framing_stage` → artifact writers → `.stage_done/missing_framing`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/gap_evaluations.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Real LLM; shard/coverage fail-open
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `_run_missing_framing_stage`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `framing-shard`
- Status: OPEN_RISK

### STG-mastering_plan_confirm — stage `mastering_plan_confirm`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mastering_plan_confirm`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["mastering_plan_confirm"]` → `interview_mux.mastering_shape_runtime.run_mastering_plan_confirm` → artifact writers → `.stage_done/mastering_plan_confirm`
- Prompt / schema / artifact: docs/prompts/mastering/* (mostly unwired soft-gate) — see SYN-SHAPE-01; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Gap-count heuristic before compose
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.mastering_shape_runtime.run_mastering_plan_confirm`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `research-shape-llm-cutover`
- Status: OPEN_RISK

### STG-gap_framing_compose — stage `gap_framing_compose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_gap_framing_compose`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["gap_framing_compose"]` → `_run_gap_framing_compose_stage` → artifact writers → `.stage_done/gap_framing_compose`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/gap_report.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Real LLM + heal ladder; binds thin plan
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `_run_gap_framing_compose_stage`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `framing-shard`
- Status: LIKELY_MITIGATED_ON_HEAD (2026-09-22 harden: StageInfo companions, analysis-era ladder skip, fill/demote honesty, warrant budget, missing_framing admit, layup flap, forward-cue flush block; residual R1 LLM content)

### STG-delivery_brief_build — stage `delivery_brief_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_delivery_brief_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["delivery_brief_build"]` → `interview_mux.delivery_brief.run_delivery_brief_build` → artifact writers → `.stage_done/delivery_brief_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Brief without incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.delivery_brief.run_delivery_brief_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-soundscape_policy_build — stage `soundscape_policy_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_soundscape_policy_build`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["soundscape_policy_build"]` → `interview_mux.soundscape_policy.run_soundscape_policy_build` → artifact writers → `.stage_done/soundscape_policy_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Policy thin → music/SFX wrong
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.soundscape_policy.run_soundscape_policy_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-episode_structure_compose — stage `episode_structure_compose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_episode_structure_compose`)
- Call graph: `dispatch_stage` → `pipeline._analysis_stage_fns["episode_structure_compose"]` → `interview_mux.episode_structure.run_episode_structure_compose` → artifact writers → `.stage_done/episode_structure_compose`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Structure after gap; order authority fights Pass1 plan
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _analysis_stage_fns; `interview_mux.episode_structure.run_episode_structure_compose`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK


---

## High-risk analysis depth cards

### STG-mastering_research-DEPTH — fail-open thin dossier (existence probes)

- Surface: stage
- Modes: Manual | Full-auto | Partial
- Brain: 0.1.0 (same host impls as 0.0.0 when conductor selects stage)
- Call graph: mastering_research_routing/waves/rollup → `mastering_research.py` `_probe`/`FIELD_PROBES` → `research/{field}.json` → dossier/`rollup.json` — **no LLM**
- Prompt: `docs/prompts/mastering/research-router.system.txt` **unwired** (spec contract only)
- Invariant: research fields honest or explicitly skipped
- Why weak: confidence from path existence only; waves 4–8 probe future/delivery artifacts mid-analysis → permanently thin; rollup re-runs all probes; catalog ~44 vs prompt “38”; no `stage_artifact_incompleteness`
- Likelihood: L3 | Severity: S2–S3
- Evidence: `mastering_research.py` write_field_report/`WAVE_FIELDS`; ANALYSIS_ORDER vs FIELD_PROBES; backlog G-d
- Fix-cluster: `hollow-done-coverage` + `research-shape-llm-cutover` (+ `FC-order-timing`)
- Status: OPEN_RISK
- Detail cards: MR-01 … MR-05 below

### STG-mastering_shape-DEPTH — soft-gate stub (not L0–L5 / critics)

- Surface: stage / LLM (unwired)
- Modes: all (soft_gate enable; fail-open degraded)
- Call graph: agenda heuristics → candidates first-N fake scores → synthesize **`cands[0]`** → plan_confirm gap-count heuristic. Optional 0.1.0 `shape_*_critique_gates` / Pareto never feed soft-gate synthesize. Critics: “LLM calls land with Shape Engine runtime” — **no invoker**.
- Why weak: docs/prompts mastering L0–L5 / flagship / critics are cutover contracts; production is deterministic compiler + gap LLMs only
- Likelihood: L3 | Severity: S2–S3
- Evidence: `mastering_shape_runtime.py`; `mastering_critics.py` header; prompts README “Until cutover…”
- Fix-cluster: `research-shape-llm-cutover` (+ `FC-critics-loop`, `FC-pass2-confirm`)
- Status: OPEN_RISK
- Detail cards: MS-01 … MS-03, MP-01 … MP-03, HX-01 below

### STG-framing_posture-DEPTH — advisory vs operator authority

- Surface: stage / gate
- Modes: all (0.1.0)
- Call graph: framing_posture_decide LLM → recommended_framing hint; G-Framing Yes/No sticky
- Why weak: UI may present advisory as decision; auto-Yes race
- Likelihood: L2 | Severity: S2
- Evidence: framing_posture prompts; operator-gates
- Fix-cluster: `g-framing-authority`
- Status: OPEN_RISK

### STG-boundary_detection-DEPTH — shared boundaries invalidation

- Surface: stage
- Modes: all
- Call graph: boundary_detection LLM → segments/boundaries.json; clear_from / lifecycle shared with BTR
- Why weak: self-stale clear_from on shared artifact; ITR escape hatch over-delete
- Likelihood: L2 | Severity: S3
- Evidence: artifact_lifecycle; artifact_auto_resolve escape
- Fix-cluster: `invalidation-blast`
- Status: OPEN_RISK

---

## Mastering/gap enrichment (from research agent — HEAD identify-only)

0.1.0 note: conductor can `run_stage_*` but seed-front pin + `walk_seed_remainder` keep the same ANALYSIS_ORDER as 0.0.0 linear walk for these stages. Soft-gate host impls are shared.

### MR-01 — Research is existence probe, not research
- Surface: `mastering_research_routing` / `_waves` / `_rollup`
- Modes: always-on deterministic; fail-open `skipped_or_thin`
- Call graph: pipeline → `mastering_research.run_mastering_research_*` → `_probe`/`FIELD_PROBES` → write `research/{field}.json` → dossier/rollup. **No LLM.**
- Why weak: Confidence 0.8/0.2 from path existence only; no field analysis, no router dispositions
- Likelihood: L3 | Severity: S2 | Status: OPEN_RISK
- Evidence: `mastering_research.py` `write_field_report`/`_probe`; `research-router.system.txt` unwired
- Fix-cluster: `research-shape-llm-cutover`

### MR-02 — Router prompt vs hardcoded sequential waves
- Surface: `mastering_research_routing`
- Modes: writes `mode: sequential_waves` only
- Call graph: `run_research_routing` → static `WAVE_FIELDS` → `routing.json`
- Why weak: Spec wants per-field dispositions; runtime never reads router prompt or `ROUTING_DEFAULTS.max_deep_fields`
- Likelihood: L3 | Severity: S2 | Status: OPEN_RISK
- Evidence: `run_research_routing`; prompts README “spec contracts”
- Fix-cluster: `research-shape-llm-cutover`

### MR-03 — Waves probe future/delivery artifacts mid-analysis
- Surface: waves 4–8 inside analysis order (before gap + delivery)
- Modes: thin-by-construction for late artifacts
- Call graph: research stages sit before `missing_framing` / compose / delivery, yet `FIELD_PROBES` includes gap/selection/edl/mix/master.wav
- Why weak: Dossier permanently marks decisive fields thin; Shape evidence sees hollow late half
- Likelihood: L3 | Severity: S3 | Status: OPEN_RISK
- Evidence: `v2/config.py` ANALYSIS_ORDER vs `FIELD_PROBES`
- Fix-cluster: `research-shape-llm-cutover` / order-timing

### MR-04 — Rollup re-runs routing+all waves (duplicate + no delta)
- Surface: `mastering_research_rollup`
- Modes: idempotent overwrite
- Call graph: `run_research_rollup` → routing + all waves again → dossier + rollup (same payload)
- Why weak: Waves already wrote field reports; rollup is second full probe with no enrichment
- Likelihood: L2 | Severity: S1 | Status: OPEN_RISK
- Evidence: both waves and rollup call `run_research_wave`
- Fix-cluster: `research-shape-llm-cutover`

### MR-05 — Field catalog drift (runtime ≈44 vs prompt “38”)
- Surface: research catalog / router contract
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Evidence: `WAVE_FIELDS` union vs `research-router.system.txt` line 1
- Fix-cluster: `research-shape-llm-cutover`

### MS-01 — Shape agenda is heuristics, not L0 meta-architect
- Surface: `mastering_shape_agenda`
- Modes: soft_gate enable; exception → degraded agenda
- Call graph: `compile_shape_evidence` → `_style_hints` + `nearest_mode_from_priors` → hardcoded `eval_rubric.json`. Does **not** load `shape-meta-architect` / `eval-rubric-mint`
- Why weak: Rubric weights finish/recommend/mode/clarity; `nugget_density`/`sonic_weave` weight 0.0; anti-patterns static
- Likelihood: L3 | Severity: S2 | Status: OPEN_RISK
- Evidence: `mastering_shape_runtime.py`; backlog G14 pending-runtime
- Fix-cluster: `research-shape-llm-cutover`

### MS-02 — Candidates: first-N modes with fake scores (no L1–L2 LLM)
- Surface: `mastering_shape_candidates`
- Modes: `max_mode_candidates` default 2; `skip_diversity` default True
- Call graph: agenda modes → loop build cand with `0.7 - i*0.05` scores → `candidates.json`
- Why weak: No shape-l1/l2 prompts; scores ordinal fakes; competition cosmetic
- Likelihood: L3 | Severity: S3 | Status: OPEN_RISK
- Evidence: `run_mastering_shape_candidates`; L1–L5 unused in `src/`
- Fix-cluster: `research-shape-llm-cutover`

### MS-03 — Critic/audition/Pareto stack never on soft-gate path
- Surface: aspirational Shape Engine + homunculus gate tools
- Call graph: Soft-gate stops at synthesize. Optional `shape_pre/post_critique_gates` advisory; `mastering_critics` builds packets only — **no LLM invoker**
- Why weak: Critic panel + arbiter never score; synthesize ignores frontiers
- Likelihood: L3 | Severity: S3 | Status: OPEN_RISK
- Evidence: `mastering_critics.py` header; `homunculus/shape.py`; G15–G19
- Fix-cluster: `research-shape-llm-cutover` / critics-loop

### MP-01 — Plan synthesize = pick `candidates[0]` (no flagship synthesize)
- Surface: `mastering_plan_synthesize`
- Call graph: read candidates → **`chosen = cands[0]`** → `_plan_from_candidate` → `write_plan`. No `flagship-synthesize.system.txt`
- Why weak: Authoritative plan is mode prior order, not bespoke argument
- Likelihood: L3 | Severity: S3 | Status: OPEN_RISK
- Evidence: `run_mastering_plan_synthesize` ~cands[0]; flagship prompt unwired
- Fix-cluster: `research-shape-llm-cutover`

### MP-02 — Pass2 confirm is gap-count heuristic before compose
- Surface: `mastering_plan_confirm` (seed: after missing_framing, before gap_framing_compose)
- Call graph: if gap_evaluations len==0 → sparse_source; if n≥8 and sparse → guide_summary → rebuild; shadow_diff often vo_density_air 0
- Why weak: Never reads VO script quality; cannot see gap_report (compose later)
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Evidence: `run_mastering_plan_confirm`; ANALYSIS_ORDER seating
- Fix-cluster: `research-shape-llm-cutover` / pass2-confirm

### MP-03 — `ordered_segment_ids` at Pass1 usually chrono/manifest
- Surface: synthesize/confirm via `shape_order_emit.attach_shape_order`
- Call graph: prefer plan → narrative_plan (delivery) → episode_structure (after gap) → selection → **manifest chrono**
- Why weak: At Pass1 preferred sources absent → tape order; downstream air/ranking fight it
- Likelihood: L3 | Severity: S2 | Status: OPEN_RISK
- Evidence: `shape_order_emit.py` vs stage order
- Fix-cluster: `research-shape-llm-cutover` / order-timing

### GF-01 — `missing_framing`: real LLM; shard/coverage fail-open risk
- Surface: `missing_framing` → `understanding/gap_evaluations.json`
- Call graph: gates/eligibility → `gaps.run_missing_framing` → missing-framing prompt → analysis LLM or shard merge + coverage pass
- Why weak: Large tapes shard without pre-specialists; coverage for sparse shards; plan priors are soft-gate mode guesses
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Evidence: `stages/gaps.py` `run_missing_framing`; pipeline `_run_missing_framing_stage`
- Fix-cluster: `framing-shard`

### GF-02 — `gap_framing_compose`: real LLM + heal ladder; binds thin plan
- Surface: `gap_framing_compose` → `gap_report.json`
- Call graph: payload (gap evals + degraded plan summary) → compose LLM → repair/fill/demote; on LLM fail still persists healed seed
- Why weak: Consumes soft-gate plan narrative_mode; can ship thin VO under “complete”
- Likelihood: L2 | Severity: S3 | Status: LIKELY_MITIGATED_ON_HEAD (compose_plan_bind_mode advisory until consumers_bind; demote refuse under warrant; fill fail-closed)
- Evidence: `run_gap_framing_compose` try/except fill path; `compose_plan_bind_mode`
- Fix-cluster: `framing-shard` + pass2-confirm

### HX-01 — Prompt stock vs runtime: mastering/* mostly dead
- Surface: `docs/prompts/mastering/*` except integrity/critic plumbing registry rows
- Why weak: Operators/docs imply mutation engine; production delivers soft-gate + gap LLMs
- Likelihood: L3 | Severity: S3 | Status: OPEN_RISK
- Evidence: mastering prompts README; backlog G14–G19; mastering-process.md “Slim Shape soft-gate”
- Fix-cluster: `research-shape-llm-cutover`


---

## Mid-analysis DEEP enrichment

# Mid-ANALYSIS STG-*-DEEP (HEAD only)

Evidence = `src/`, `docs/prompts/`, stage contracts, `config/app.defaults.json`, tests. No `ASSETS/executions/`.

---

## STG-boundary_detection-DEEP

| Field | Value |
|---|---|
| **Call graph** | `pipeline` → `segmentation.run_boundaries` → (optional skip) `ideal_cuts.boundaries_already_from_ideal_cuts` + `evaluate_boundary_quality` **OR** `run_analysis_llm_stage` → `llm_simple` → `make_stage_persist(segments/boundaries.json)` → `boundary_edge_score.apply_boundary_confidence_pass` → `_assert_boundary_quality` (+ optional `enforce_max_segment_duration`) |
| **Prompts** | `docs/prompts/segmentation/boundary-detection.system.txt` · OA-03 · volley `full/shard/collate` · arbiter `docs/prompts/_shared/arbiter-rubrics/boundary_detection.json` · examples `boundary-detection.examples.md` · refine sibling `boundary-detection-refine.system.txt` (used later) |
| **Why weak** | Ideal-cuts bind can **skip LLM** when quality report doesn’t reject; sparse keep-windows are the designed poison if `reject_coarse_fallback` is off. Spine attach uses a **capped** boundary volley (`BOUNDARY_VOLLEY_MAX_SPINE_EVENTS` / spread sample) — docs already warn truncation. Pause-ladder thinning by pace can starve split hints. Quality assert deliberately ignores self-labeled “coarse/token” warnings (metrics-only) — good for false positives, weak if metrics lie. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` (skip + truncation junctions); quality assert = `LIKELY_MITIGATED_ON_HEAD` for warning-keyword false fails |
| **fix-cluster** | `SEG-BOUNDARY-AUTHORITY` |
| **Evidence** | `src/interview_mux/stages/segmentation.py` (`run_boundaries`, `_assert_boundary_quality`) · `interview_spine/compact.py` · `docs/workflows/troubleshooting.md` (volley truncated) · contract `docs/cross-cutting/stage-contracts/boundary_detection.yaml` |

---

## STG-segment_classification-DEEP

| Field | Value |
|---|---|
| **Call graph** | `segmentation.run_classification` → `restamp_run_span_speakers` → `talking_points_authority.try_deterministic_classification` (ideal-cuts short-circuit) **OR** `build_classification_payload` → `run_analysis_llm_stage` / batched `run_llm_stage_simple` (obligation shards) → persist transform `stamp_span_speakers` + role/type repair → `maybe_run_post_stage_specialists` → `bootstrap_manifest_topic_tags` → `refresh_selection_seed_from_boundaries` → `sync_speech_sidecars` |
| **Prompts** | `docs/prompts/segmentation/segment-classification.system.txt` (+ TBIY variant via `prompt_variant`) · OA-04 · arbiter `segment_classification.json` · examples `segment-classification.examples.md` |
| **Why weak** | Deterministic ideal-cuts path can stamp types without LLM judgment. Batched path merges by `required_segment_ids` and **hard-raises** if any id missing — thrash under truncation. Lint only catches “all `interviewee_answer`” (with allowance), not wrong Q/A role flips beyond transform heuristics. Topic tags often empty until bootstrap. Nested re-entry from `boundary_topic_resplit` can race staging. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `SEG-CLASSIFY-OBLIGATION` |
| **Evidence** | `stages/segmentation.py` (`run_classification`) · `deterministic_lint._lint_segment_classification` · contract `segment_classification.yaml` · scorecard P0 shipped |

---

## STG-content_brief_reanchor-DEEP

| Field | Value |
|---|---|
| **Call graph** | `understanding.run_content_brief_reanchor` → `bootstrap_manifest_topic_tags` → `run_analysis_llm_stage` (`content-brief-reanchor.system.txt`) with compact manifest + id-only boundaries + spine/coherence/conversation → persist must be `artifact_status_for_stage == complete` → `sync_content_brief_reanchor_to_state` → `maybe_run_coherence_analysis(phase=post_reanchor)` |
| **Prompts** | `docs/prompts/understanding/content-brief-reanchor.system.txt` · OA-05 · arbiter `content_brief_reanchor.json` · examples in coherence-orc03 examples |
| **Why weak** | Packet **drops** boundary text (ids/times only) and caps topic excerpts (~40×240 chars) — topic↔segment anchoring can drift. Completeness gate can fail/heal thrash if topics empty. After resplit, `_patch_brief_ids_after_resplit` is best-effort prefix remap (not semantic). Crossval `post_reanchor` helps but does not fix thin volleys. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` (anchor drift); completeness refuse = partial mitigate |
| **fix-cluster** | `BRIEF-REANCHOR-IDS` |
| **Evidence** | `stages/understanding.py` (`run_content_brief_reanchor`) · `segmentation._patch_brief_ids_after_resplit` · lint `_lint_content_brief_reanchor` · contract `content_brief_reanchor.yaml` |

---

## STG-framing_posture_decide-DEEP

| Field | Value |
|---|---|
| **Call graph** | `framing_posture_decide.run_framing_posture_decide` → skip if not `is_homunculus_run` / disabled → monologue: `build_monologue_decision` + `persist` + `apply_host_gate` **OR** `run_analysis_llm_stage` → `build_framing_posture_input` → persist `advisory_only` → `apply_host_gate` (`ensure_gap_fill_skipped` only when `native_only` + deterministic/operator decided_by) |
| **Prompts** | `docs/prompts/framing/framing-posture-decide.system.txt` · catalog id **OA-09** (collides with `talking_points_compose` in `STAGE_PRIMARY_IDS`) · flagship tier · schema `framing_posture_decision.schema.json` |
| **Why weak** | **0.0.0 brain never runs** (heal-skip). Output is advisory; LLM `native_only` is **not** enforced by `apply_host_gate` (only deterministic/operator). Contract lists empty hard inputs — prestage won’t catch missing brief/manifest. Catalog ID collision muddies OA-* forensics. Wrong `yes`/`sparse` only affects gate UX until operator G-Framing. |
| **L/S** | **L2 / S2** (S3 if operator trusts advisory blindly in Full-auto UI) |
| **Status** | `OPEN_RISK` (advisory + ID collision); host_enforce for true monologue = `LIKELY_MITIGATED_ON_HEAD` |
| **fix-cluster** | `FRAMING-POSTURE-ADVISORY` |
| **Evidence** | `stages/framing_posture_decide.py` · `framing_posture.py` · `llm_interaction_registry.py` (OA-09 dual map) · `tests/test_framing_posture_decide.py` · contract `framing_posture_decide.yaml` |

---

## STG-boundary_topic_resplit-DEEP

| Field | Value |
|---|---|
| **Call graph** | `run_boundary_topic_resplit` → cycle guard (`run_meta.boundary_topic_resplit_cycle_done`) / ideal-cuts skip / no-boundaries hollow stamp → `detect_overloaded_segment_ids` → if overload: LLM refine (`boundary-detection-refine.system.txt`) **if** `segmentation_policy.resegment_pass` else deterministic `enrich_boundary_rows` → unlink class/reanchor `.stage_done` + `clear_from(next)` → `split_plan` auto-apply → edge confidence → nested `run_nested_staged_stage(segment_classification)` + `content_brief_reanchor` → brief id patch |
| **Prompts** | `docs/prompts/segmentation/boundary-detection-refine.system.txt` · OA-03 (shared with boundary_detection) · only when `resegment_pass` (default **true** when granularity=`fine`) |
| **Why weak** | Heaviest mid-analysis footgun: **invalidation + nested re-run** of classification/reanchor; cycle flag prevents infinite loop but one-shot can still thrash staging. Ideal-cuts skip leaves overloaded multi-topic segments unfixed. Hollow `mark_done_raw` when no boundaries. Auto `split_plan` can grow boundary count and cascade rerank markers. Brief id patch is prefix-heuristic. |
| **L/S** | **L3 / S4** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `SEG-RESPLIT-INVALIDATION` |
| **Evidence** | `stages/segmentation.py` (`run_boundary_topic_resplit`) · `segment_timeline_standard.resolved_segmentation_policy` · `tests/test_boundary_topic_resplit.py` · contract `boundary_topic_resplit.yaml` · `write_staging` nested note |

---

## STG-vernacular_segment_sanitize-DEEP

| Field | Value |
|---|---|
| **Call graph** | `audio_probes.run_vernacular_segment_sanitize` → read `transcript/protected_zones.json` → `vernacular_sanitize.sanitize_manifest_with_zones` → merge flow `audio_tags` → write `segments/manifest.json`, `vernacular/resplit_report.json`, `analysis/vernacular_must_keep.json`, update zones · **no LLM** |
| **Prompts** | — (deterministic; covenant docs `vernacular-evidence-covenant.md`) |
| **Why weak** | Default `audio_probes.enforcement_mode` = **`shadow`** — must_keep recorded but not hard-enforced. `fail_open=true`: missing/corrupt zones/manifest → early return without hard fail (pipeline may still mark done via wrapper). Writes `manifest.json` **without `stage_key`** — staging/lifecycle fingerprint risk vs classification publisher. Empty zones → no-op protection. Can invent child segment_ids that later stages must remap. |
| **L/S** | **L2 / S3** (S4 if special speech cut under shadow) |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `VERNACULAR-SHADOW-ENFORCE` |
| **Evidence** | `stages/audio_probes.py` · `vernacular_sanitize.py` · `config/app.defaults.json` (`enforcement_mode: shadow`) · contract `vernacular_segment_sanitize.yaml` (empty outputs) |

---

## STG-low_conf_island_scan-DEEP

| Field | Value |
|---|---|
| **Call graph** | `low_conf_fuse_stages.run_low_conf_island_scan` → `low_conf_islands.run_low_conf_island_scan` (word ladder → `analysis/low_conf_islands.json`) → `compute_density_ranking` → `write_low_conf_must_keep` → optional `high_value_speech_islands.scan` + `mark_segments_high_value` (fail-open) · **no primary LLM** (STT lexicon specialist is on ranking, not this stage) |
| **Prompts** | — for scan; related later: `stt-lexicon-island-verify.system.txt` (OS-04 on `full_master_ranking`) · island structure LLM is inside fuse (`island-cluster-structure-adjudicate.system.txt`, OF-02b) |
| **Why weak** | Recall-first thresholds (`low_confidence_threshold: 0.85`, top **10%** must_keep `authoritative`) can over-include noisy islands into hard keep — selection bloat. Disabled/missing transcript → empty doc, still “complete.” High-value scan fails open. Soft islands / null conf treated as mid can skew density. No schema on `analysis/low_conf_islands.json` in contract. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `LOWCONF-MUSTKEEP-DENSITY` |
| **Evidence** | `stages/low_conf_fuse_stages.py` · `low_conf_islands.py` · `config/app.defaults.json` `analysis.low_conf_selection` · contract `low_conf_island_scan.yaml` |

---

## STG-connector_fuse_pass-DEEP

| Field | Value |
|---|---|
| **Call graph** | `low_conf_fuse_stages.run_connector_fuse_pass(pass_id=post_sanitize)` → `segment_fuse.run_connector_fuse_pass` → HV cluster fuse (`adjudicate_island_cluster_structure` / OF-02b) → forced diarization fuses → loop: `enumerate_seam_packets` → `adjudicate_seams` → `adjudicate_seams_llm` (economy → standard → flagship) **or** `deterministic_fallback_verdict` → `apply_connector_fuses` until fixed point / osc halt / cap → air-bounds + encompass |
| **Prompts** | `docs/prompts/segmentation/connector-seam-adjudicate.system.txt` (OF-02a) · `docs/prompts/segmentation/island-cluster-structure-adjudicate.system.txt` (OF-02b) |
| **Why weak** | Defaults: `max_fuse_rounds=0` / `max_fuses_per_pass=0` → treated as **~unlimited** (10k). Economy LLM + `deterministic_fallback_on_llm_fail` + `prefer_fuse_when_hint_and_uncertain` can over-fuse incomplete thoughts. Manifest rewrite remaps ids → downstream brief/sonic/selection drift. Oscillation halt leaves `fixed_point=false` without hard fail. Stage not in `ALL_LLM_STAGES` despite nested LLM. Pass repeats later (`pre_ranking`, `junction_heal`). |
| **L/S** | **L3 / S4** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `CONNECTOR-FUSE-THRASH` |
| **Evidence** | `segment_fuse.py` (`run_connector_fuse_pass`, `adjudicate_seams_llm`) · `island_cluster_structure.py` · `config/app.defaults.json` `analysis.connector_fuse` · contract `connector_fuse_pass.yaml` |

---

## STG-sonic_context_build-DEEP

| Field | Value |
|---|---|
| **Call graph** | `sonic_context_stages.run_sonic_context_build` → `sonic_context.build_sonic_context` (`classify_atlas_bucket` keyword/heuristic → `build_tag_registry` → cues/mix_policy) → `write_validated_artifact(understanding/sonic_context.json)` → `mark_done` · **no LLM** |
| **Prompts** | — |
| **Why weak** | Atlas bucket is **heuristic**: trauma word hits ≥2, overlap/crosstalk → `noisy_room`, jargon word list, “debate/argue” in blob — easy mis-bucket. That seeds `SCENARIO_POSTURE` bans/caps for all later SFX. Contract has **empty outputs/inputs** vs real artifact. Tag registry is topic-name/keyword scrape, not listen judgment. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `SONIC-ATLAS-HEURISTIC` |
| **Evidence** | `sonic_context.py` (`classify_atlas_bucket`, `build_sonic_context`) · `stages/sonic_context_stages.py` · fixtures under `tests/fixtures/sonic_context/` · contract `sonic_context_build.yaml` · troubleshooting trauma/stinger note |

---

## STG-sound_design_palettes-DEEP

| Field | Value |
|---|---|
| **Call graph** | `sound_design_stages.run_sound_design_palettes` → if `sound_design.early_palettes_llm=false` (**default**): seed empty `palettes` + deferred `sonic_identity` from atlas/tags → `heal_or_refuse_mark` **ELSE** `run_analysis_llm_stage` (`theme-palettes.system.txt`) → merge palettes + `align_palette_keywords_to_sonic_context` |
| **Prompts** | `docs/prompts/sound_design/theme-palettes.system.txt` (+ TBIY variant) · OA-06 · arbiter `sound_design_palettes.json` · examples `sound-design-palettes.examples.md` — **usually unused at HEAD default** |
| **Why weak** | Stage is **LLM-capable but deferred by default** — scorecard “shipped” overstates runtime LLM. Empty palettes intentionally; lint short-circuits when deferred. Downstream `sound_design_plan` must invent musical direction late; early consumers of `coherence.sonic_identity` get atlas seed only. If `early_palettes_llm=true`, provenance lint depends on thin sonic tags. |
| **L/S** | **L2 / S2** (S3 when SDP inherits weak identity) |
| **Status** | `OPEN_RISK` (hollow early stage by design) |
| **fix-cluster** | `PALETTES-DEFERRED-EMPTY` |
| **Evidence** | `stages/sound_design_stages.py` · `config/app.defaults.json` `early_palettes_llm: false` · `deterministic_lint._lint_sound_design_palettes` · `docs/cross-cutting/mastering-process.md` · contract `sound_design_palettes.yaml` |

---

## STG-delivery_brief_build-DEEP

| Field | Value |
|---|---|
| **Call graph** | `delivery_brief.run_delivery_brief_build` → `build_delivery_brief` (source duration ratios, gap counts, VO floor from `gap_framing` ratios, flow_adaptation sfx/weights, optional TBIY `refresh_conformance`) → write `understanding/delivery_brief.json` → `update_completion_from_analysis` / `maybe_auto_verify_profile` · **no LLM** |
| **Prompts** | — · composed schema exists (`analysis_envelope_delivery_brief_build.openai.json`) but stage is deterministic |
| **Why weak** | Soft formula: `ideal_fraction_of_source=0.65`, `question_budget_max=0` (**uncapped** → budget follows gap count + VO floor). Runs **after** `gap_framing_compose` in `ANALYSIS_ORDER` but **before** ranking/selection — `ordered_n` often falls back to segment count → VO floor mis-scaled. Disabled path writes zeroed stub still “done.” No arbiter. Budgets can conflict with later selection duration enforcement. |
| **L/S** | **L2 / S2** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `DELIVERY-BRIEF-SOFT-BUDGET` |
| **Evidence** | `delivery_brief.py` · `config/app.defaults.json` `analysis.delivery_brief` · contract `delivery_brief_build.yaml` (hard: `gap_report`) · `v2/config.py` order |

---

## STG-soundscape_policy_build-DEEP

| Field | Value |
|---|---|
| **Call graph** | `soundscape_policy.run_soundscape_policy_build` → require `delivery_brief.json` → `build_policy(refresh_slots=True)` (SAP + sonic mix + brief density + creative overrides + `score_cue_slots`) → `validate_soundscape_policy` → write policy · **no LLM** · disabled → `mark_done` skip |
| **Prompts** | — (scorecard: Prompt/Arbiter `—`, Examples `doc_only`) |
| **Why weak** | Cue slots scored from prior sonic/brief heuristics — garbage-in from wrong atlas. Creative-delivery overrides can fight `source_music_risk` high→sparse clamp. Hard require on delivery_brief only; sonic/SAP soft-empty still produce a policy. No arbiter/examples depth. Slot binding to speaker volleys is best-effort. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `SOUNDSCAPE-POLICY-HEURISTIC` |
| **Evidence** | `soundscape_policy.py` (`build_policy`, `run_soundscape_policy_build`) · scorecard P2 row · contract `soundscape_policy_build.yaml` · schema `soundscape_policy.schema.json` |

---

## STG-episode_structure_compose-DEEP

| Field | Value |
|---|---|
| **Call graph** | `episode_structure.run_episode_structure_compose` → **`_assert_boundary_quality`** (late hard-stop) → `build_episode_structure` (pack axes + STD/DYN slot scoring + hook reel + speaker volleys) → `persist_structure` → `update_completion_from_analysis` + `maybe_finalize_shared_analysis` → `mark_done` · **no LLM** (explicitly not in `QUALITY_LOCAL_ALLOWLIST`) |
| **Prompts** | — (LX-03 reserved note in code; no OpenAI stage) |
| **Why weak** | Analysis handoff can **hard-fail** on boundary metrics here after fuse/sanitize already mutated timeline. Slot plan binds **all** segments to `STD_act_body` only — cold-open/hook heuristic; dynamic slots unbound. Pack omit_reasons can drop structure silently. Disabled → empty mark_done. No invalidation consumers in contract. Thin structure → weak downstream narrative/SFX placement priors. |
| **L/S** | **L2 / S3** |
| **Status** | `OPEN_RISK` |
| **fix-cluster** | `EPISODE-STRUCTURE-LATE-BOUNDARY` |
| **Evidence** | `episode_structure.py` (`build_episode_structure`, `run_episode_structure_compose`) · `tests/test_episode_structure.py` · contract `episode_structure_compose.yaml` · `pipeline.py` `analysis_complete` tied to this stage |

---

## Ranked open junctions (mid-ANALYSIS)

1. **SEG-RESPLIT-INVALIDATION** — boundary_topic_resplit nested class/reanchor + clear_from  
2. **CONNECTOR-FUSE-THRASH** — unlimited rounds + economy/fallback overfuse + id remap  
3. **SEG-BOUNDARY-AUTHORITY** — ideal-cuts skip + spine volley truncation  
4. **VERNACULAR-SHADOW-ENFORCE** — shadow mode + unstaged manifest write  
5. **SONIC-ATLAS-HEURISTIC** → **PALETTES-DEFERRED-EMPTY** → **SOUNDSCAPE-POLICY-HEURISTIC** cascade  
6. **BRIEF-REANCHOR-IDS** / **SEG-CLASSIFY-OBLIGATION** / **LOWCONF-MUSTKEEP-DENSITY** / **DELIVERY-BRIEF-SOFT-BUDGET** / **FRAMING-POSTURE-ADVISORY** / **EPISODE-STRUCTURE-LATE-BOUNDARY**

---

## Early-analysis DEEP enrichment

# Early ANALYSIS — STG-*-DEEP (HEAD identify-only)

Rubric: **L**1–3 / **S**1–4 per pre-run failure audit. Evidence = current `src/` + `docs/prompts/` only (no `ASSETS/executions/`).

---

### STG-audio_preclean-DEEP
- **Call graph:** `pipeline` → `stages.audio_preclean.run_audio_preclean` → `_selected_scope` / `ensure_preclean_skipped` → `_enhance_source_to_output` → `deepfilter_runner.enhance_wav` / `enhance_wav_batch` **or** `ffmpeg_denoise.denoise_wav`; chunk path: `audio_timeline.chunk_wav_by_max_bytes` → `concat_clips_with_crossfade` → `preclean/isolated.wav` + `lineage.json`
- **Prompt:** N/A (local DeepFilterNet / FFmpeg)
- **Why weak:** `config/app.defaults.json` + `_selected_scope` default `auto_run_before_ingest=true` / `default_action=run` **mutates** `run_meta.audio_preclean` to accept — contradicts operator-gate “Preclean never auto-run.” Unavailable DeepFilter silently falls through to `ffmpeg_local` (`local_fallback_enabled` default true). Chunk merge uses assembly crossfade ms, so large sources can get seam coloration without operator signal beyond a log line.
- **L/S:** L3 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `preclean-auto-vs-offer`
- **Evidence:** `src/interview_mux/stages/audio_preclean.py` (`_selected_scope`, `_enhance_source_to_output`, `_enhance_source_with_deepfilter`); `config/app.defaults.json`; `docs/workflows/operator-gates.md` / AGENTS Preclean rule; `tests/test_audio_preclean.py`

---

### STG-ingest-DEEP
- **Call graph:** `stages.ingest.run_ingest` → `_ingest_source` (prefers `preclean/isolated.wav`) → `source_loudness.apply_preclean_leveling_policy` + `build_ingest_loudness_filter` → `operator_subprocess.run_logged_command(ffmpeg)` → `ingest/normalized.wav` + `loudness.json` + `checksums.json` → fail-open `homunculus.source_card.refresh_source_profile` / `source_readiness.write_source_readiness`
- **Prompt:** N/A
- **Why weak:** FFmpeg input may be preclean isolated, but checksums always hash `ctx.input_audio()` as `source_sha256` and only optionally add `preclean_sha256` — lineage readers that treat `source_sha256` as “what was normalized” disagree with the actual ffmpeg `-i`. Loudness skip-upward after preclean is intentional; fail-open profile/readiness hides selection errors.
- **L/S:** L2 / S1
- **Status:** OPEN_RISK
- **fix-cluster:** `ingest-lineage-checksum`
- **Evidence:** `src/interview_mux/stages/ingest.py` (`_ingest_source`, checksum block); `src/interview_mux/source_loudness.py` (`apply_preclean_leveling_policy`)

---

### STG-transcribe-DEEP
- **Call graph:** `stages.transcribe_local.run_transcribe` → `stt_runner.transcribe_audio` → `local_runtime.run_runtime_script("speech","tools/stt_transcribe.py")` → `transcript_normalize.normalize_local_stt` (**`_infer_turn_speakers`**) → `transcript/full.json` + `transcript/speakers.json`
- **Prompt:** N/A (local MLX STT; model via `local_speech` / speech selection)
- **Why weak:** Hard Apple-Silicon + speech-venv gate (honest fail). After that, if diarization returns **one** speaker id, `_infer_turn_speakers` **invents** alternating `spk_0`/`spk_1` on ≥700 ms pauses — fake two-speaker tape before G0. Bare `except` around source_card; no STT retry beyond single subprocess.
- **L/S:** L3 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `stt-fake-diarization`
- **Evidence:** `src/interview_mux/stages/transcribe_local.py`; `src/interview_mux/stt_runner.py` (`transcribe_audio`); `src/interview_mux/transcript_normalize.py` (`_infer_turn_speakers`, `normalize_local_stt`)

---

### STG-transcript_review_build-DEEP
- **Call graph:** `stages.transcript_review.run_transcript_review_build` → `_build_chunks` / `_refine_chunk_edges` (`snap_cut_to_word_boundary`, `find_silence_valley_ms`) → `audio_clips.extract_clip` → `validate_transcript_review_queue` → `transcript/review_queue.json`; G0 close path: `mark_transcript_review_complete` → `materialize_transcript` → `apply_corrections` → `_apply_correction_to_range` / `_replace_words_in_range`
- **Prompt:** N/A (deterministic G0 queue; operator edits)
- **Why weak:** Dock word edits set chunk `reviewed=True` while correction entry stays `reviewed=False`; `_apply_correction_to_range` **no-ops** when span is `dock_corrected`, and token-count mismatch **collapses** a range to one synthetic word (`_replace_words_in_range`) — destroys word timing for SAP/spine/ideal cuts. `maybe_auto_complete_transcript_review` returns False (good), but stage marks `transcript_review_build` done while G0 gate is separate — easy hollow “build done / review open” confusion. Missing word confidences → confidence `0.0` → everything `needs_review`.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `g0-correction-materialize`
- **Evidence:** `src/interview_mux/stages/transcript_review.py` (`_sync_review_queue_from_word_edits`, `_apply_correction_to_range`, `_replace_words_in_range`, `maybe_auto_complete_transcript_review`)

---

### STG-audio_probe_build-DEEP
- **Call graph:** `stages.audio_probes.run_audio_probe_build` → `audio_probe_orchestrator.build_audio_probe_artifacts` (`build_speaker_flows`, probe packs, optional `audio_probe_mlx`) → writes `analysis/run_golden_facts.json`, `transcript/protected_zones.json`, `transcript/speaker_flows.json`, `vernacular/probe_report.json`; completion via `write_staging.after_stage_write_check` → `mark_done` (stage does **not** call `mark_done` itself)
- **Prompt:** N/A (heuristic + optional local ML listen)
- **Why weak:** `fail_open=true` default: any build exception → `empty_probe_artifacts(...)` still written and committed as success. Default `enforcement_mode=shadow` so vernacular must_keep is advisory (`authoritative_must_keep_ids` only hard when authoritative). Missing/unreadable `ingest/normalized.wav` continues without clips. Hollow goldens look “done” to agenda/`prepare_outputs`.
- **L/S:** L3 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `audio-probe-failopen-shadow`
- **Evidence:** `src/interview_mux/stages/audio_probes.py` (`run_audio_probe_build`); `src/interview_mux/audio_probe_orchestrator.py` (`build_audio_probe_artifacts`, `empty_probe_artifacts`); `tests/test_audio_probes.py`

---

### STG-source_acoustic_profile-DEEP
- **Call graph:** `stages.understanding.run_source_acoustic_profile` → `_derive_pacing(transcript)` + `_derive_energy_profile(preclean|normalized)` → `_derive_mix_contract` / `_derive_prosody_summary` → `understanding/source_acoustic_profile.json`
- **Prompt:** N/A (feeds later LLM `source_acoustic_pacing` / mix tokens)
- **Why weak:** Pipeline order is SAP **before** `interview_spine_build`, but `_derive_prosody_summary` only upgrades F0 when spine already exists — happy path always ships default `f0_band=mid` / `f0_variability=moderate` unless operator hits `recompute-acoustic-profile` later. Energy fields named `*_lufs` are dBFS window percentiles (mislabel). `source_music_risk` silence/phrase heuristic can force `underscore_policy=skip` into mix contracts.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `sap-prosody-order`
- **Evidence:** `src/interview_mux/stages/understanding.py` (`run_source_acoustic_profile`, `_derive_prosody_summary`, `_derive_energy_profile`); `src/interview_mux/v2/config.py` order; `tests/test_source_acoustic_profile_prosody.py` (spine-preseed only)

---

### STG-interview_spine_build-DEEP
- **Call graph:** `stages.interview_spine_stage.run_interview_spine_build` → `diarization_suspicion.run_diarization_verify` (may **rewrite** `transcript/full.json` + speakers + rebuild flows) → `can_skip_rebuild` → `build_windows` / `enrich_window_features` / `build_boundary_events` / `build_clap_index` → validate → `understanding/interview_spine.json`
- **Prompt:** N/A (CLAP / DSP local)
- **Why weak:** Runs **after G0**. Verify YES pairs relabel words and rewrite the signed-off transcript fail-open on MLX errors (labels kept, but successful YES mutates post-review tape). CLAP fail-open leaves retrieval disabled. Spine consumers treat windows/boundaries as authoritative while G0 operator never re-sees relabels.
- **L/S:** L3 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `spine-post-g0-relabel`
- **Evidence:** `src/interview_mux/stages/interview_spine_stage.py`; `src/interview_mux/diarization_suspicion.py` (`run_diarization_verify` write of `transcript/full.json`); `tests/test_diarization_suspicion.py`

---

### STG-speaker_roles-DEEP
- **Call graph:** `understanding.run_speaker_roles` → `build_speaker_role_evidence` + stratified samples (`speaker_roles_sample_chars` default 24k) → `stages.analysis_stage.run_analysis_llm_stage` → `llm_simple.run_llm_stage_simple` → persist `enrich_speakers_artifact` → `sync_speakers_to_state`; lint via `deterministic_lint._lint_speaker_roles`; recovery `speaker_roles_dominant_fallback` in `pipeline.run_single_stage`
- **Prompt:** `docs/prompts/understanding/speaker-roles.system.txt`
- **Why weak:** Long interviews only see sampled windows — roles can miss a quiet host. Lint mainly flags all-`unknown` / panel count / blocking `role_tape_conflict`, not wrong confident swap. Max 2 LLM attempts; wrong roles poison topology pickup + gap clone host. Dominant-fallback recovery can skip LLM re-run after playbook — mitigates stuckness, not wrong labels.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `roles-sample-poison-topology`
- **Evidence:** `src/interview_mux/stages/understanding.py` (`run_speaker_roles`); `docs/prompts/understanding/speaker-roles.system.txt`; `src/interview_mux/deterministic_lint.py` (`_lint_speaker_roles`); `src/interview_mux/pipeline.py` (dominant_fallback branch)

---

### STG-source_topology_build-DEEP
- **Call graph:** `source_topology.run_source_topology_build` → `build_topology_artifacts` (`_speaker_talk_stats`, `classify_topology`, `resolve_clone_host_speaker_id`) → writes `understanding/source_topology.json` + `flow_adaptation.json` → `maybe_auto_confirm_pickup_speaker` (Full-auto)
- **Prompt:** N/A (deterministic; consumes speaker_roles artifact)
- **Why weak:** TBIY path calls `build_conformance_plan(..., pickup_id=least)` where `least` is quietest **overall** talk_ms, not the resolved clone-host `pickup_id` — conformance/recovery can target the wrong voice. `_segmentation_policy` ignores `topology_class` (`_ = topology_class`). Empty/unknown roles fall through to `one_on_one_asymmetric`. Full-auto may `confirm_pickup_speaker` without human G-Framing.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `topology-pickup-conformance`
- **Evidence:** `src/interview_mux/source_topology.py` (`build_topology_artifacts` lines ~465–519, `classify_topology`, `maybe_auto_confirm_pickup_speaker`)

---

### STG-content_context-DEEP
- **Call graph:** `understanding.run_content_context` → single `run_analysis_llm_stage` **or** proactive `transcript_shards.build_transcript_shards` × `run_llm_stage_simple` → `merge_content_brief_artifacts` → persist `understanding/content_brief.json` + post hooks (`maybe_auto_extract_value_features`, `maybe_run_coherence_analysis`)
- **Prompt:** `docs/prompts/understanding/content-context.system.txt` (TBIY: `content-context.tbiy.system.txt` via `prompt_variant`)
- **Why weak:** Shard path uses `_noop_persist` per shard then merge — partial shard failures drop silently until `parts` empty (hard fail). Merge can dilute thesis/topics vs single-pass; lint (`_lint_content_context`) catches empty thesis / unanchored topics but not subtle wrong thesis. Full-text (non-shard) packs entire transcript into the LLM packet — context pressure / truncation risk on mid-length tapes under shard threshold.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `brief-shard-merge`
- **Evidence:** `src/interview_mux/stages/understanding.py` (`run_content_context`); `src/interview_mux/transcript_shards.py` (`merge_content_brief_artifacts`); `docs/prompts/understanding/content-context.system.txt`

---

### STG-talking_points_compose-DEEP
- **Call graph:** `understanding.run_talking_points_compose` → (if `ideal_cuts.enable`) LLM via `run_analysis_llm_stage` / shard `run_llm_stage_simple` → `merge_talking_points_artifacts` → `spread_talking_point_time_hints` → `understanding/talking_points.json`
- **Prompt:** `docs/prompts/understanding/talking-points-compose.system.txt`
- **Why weak:** Shard merge with zero points invents `tp_merged_empty` / “Coverage incomplete” and still `mark_done` — hollow plan seeds ideal cuts. Payload sets `transcript_samples.opening` to the **entire** shard/full text (misnamed). Disable path writes stub + `heal_or_refuse_mark(..., force=True)` so downstream “works” with fake TP.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **fix-cluster:** `tp-hollow-merge`
- **Evidence:** `src/interview_mux/stages/understanding.py` (`run_talking_points_compose`); `src/interview_mux/transcript_shards.py` (`merge_talking_points_artifacts` empty placeholder)

---

### STG-ideal_cuts_propose-DEEP
- **Call graph:** `understanding.run_ideal_cuts_propose` → `run_analysis_llm_stage` + persist: `cut_span_coverage_ratio` / `redistribute_clustered_cuts` (only if `duration_ms >= 900_000`) → `understanding/ideal_cuts.json`
- **Prompt:** `docs/prompts/understanding/ideal-cuts-propose.system.txt`
- **Why weak:** Span-coverage guard only on ≥15 min tapes — shorter interviews can ship early-clustered cuts without redistribute/raise. Disable path writes placeholder cut `0–3000ms`. Redistribute-then-`RuntimeError` is honest on long tapes (good); short-tape clustering remains unguarded.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK (long-tape span path partially guarded)
- **fix-cluster:** `cuts-span-short-tape`
- **Evidence:** `src/interview_mux/stages/understanding.py` (`run_ideal_cuts_propose` persist); `src/interview_mux/ideal_cuts.py` (`redistribute_clustered_cuts`, `ideal_cuts_cfg`); `docs/prompts/understanding/ideal-cuts-propose.system.txt`

---

### STG-ideal_cuts_materialize-DEEP
- **Call graph:** `ideal_cuts.run_ideal_cuts_materialize` → `snap_ideal_cuts` → optional `boundaries_from_snapped_cuts` + `segmentation.evaluate_boundary_quality` → may write `segments/boundaries.json` + `selection` seed → `understanding/ideal_cuts_materialized.json` → `heal_or_refuse_mark`
- **Prompt:** N/A (process / snap)
- **Why weak:** Empty snap demotes bind (tested — mitigated). **But** if `evaluate_boundary_quality` itself throws, code **fail-opens and writes** coarse ideal-cut boundaries anyway (`quality check failed … — writing boundaries`). That publishes a sparse keep-window contract that later stages treat as authoritative unless other guards catch it. Anchor reject / provisional-id strip paths exist for coarse reject — exception path bypasses them.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK (empty-snap demote = LIKELY_MITIGATED_ON_HEAD side path)
- **fix-cluster:** `cuts-bind-quality-failopen`
- **Evidence:** `src/interview_mux/ideal_cuts.py` (`run_ideal_cuts_materialize` ~1055–1109, `snap_ideal_cuts`); `tests/test_ideal_cuts.py` (`test_empty_snap_demotes_bind_mode_instead_of_raising`, `test_evaluate_boundary_quality_*`)

---

## Ranked open junctions (early analysis)

| Rank | id | L/S | Cluster |
|------|----|-----|---------|
| 1 | STG-transcribe-DEEP | L3/S2 | `stt-fake-diarization` |
| 2 | STG-interview_spine_build-DEEP | L3/S2 | `spine-post-g0-relabel` |
| 3 | STG-audio_probe_build-DEEP | L3/S2 | `audio-probe-failopen-shadow` |
| 4 | STG-audio_preclean-DEEP | L3/S2 | `preclean-auto-vs-offer` |
| 5 | STG-ideal_cuts_materialize-DEEP | L2/S3 | `cuts-bind-quality-failopen` |
| 6 | STG-source_topology_build-DEEP | L2/S2 | `topology-pickup-conformance` |
| 7 | STG-transcript_review_build-DEEP | L2/S2 | `g0-correction-materialize` |
| 8 | STG-source_acoustic_profile-DEEP | L2/S2 | `sap-prosody-order` |
