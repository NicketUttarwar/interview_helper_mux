# Delivery + Ship stage vulnerable-junction cards

Brain **0.1.0**. HEAD only. Identify-only.

Call graphs from `pipeline._delivery_stage_fns` (AST).

### STG-topic_coverage_audit — stage `topic_coverage_audit`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_topic_coverage_audit`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["topic_coverage_audit"]` → `analysis_extended.run_topic_coverage` → artifact writers → `.stage_done/topic_coverage_audit`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `master/coverage_audit.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Coverage audit soft vs ranking
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `analysis_extended.run_topic_coverage`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-narrative_arc_plan — stage `narrative_arc_plan`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_narrative_arc_plan`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["narrative_arc_plan"]` → `analysis_extended.run_narrative_arc` → artifact writers → `.stage_done/narrative_arc_plan`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `master/narrative_plan.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Arc plan vs air-order federation
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `analysis_extended.run_narrative_arc`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-chapter_close_hitch — stage `chapter_close_hitch`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_chapter_close_hitch`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["chapter_close_hitch"]` → `interview_mux.chapter_close_hitch.run_chapter_close_hitch` → artifact writers → `.stage_done/chapter_close_hitch`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `mastering/chapter_close_hitch.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Hitch without incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.chapter_close_hitch.run_chapter_close_hitch`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-connector_fuse_pass_pre_ranking — stage `connector_fuse_pass_pre_ranking`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_connector_fuse_pass_pre_ranking`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["connector_fuse_pass_pre_ranking"]` → `interview_mux.stages.low_conf_fuse_stages.run_connector_fuse_pass_pre_ranking` → artifact writers → `.stage_done/connector_fuse_pass_pre_ranking`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `analysis/connector_fuse_rounds.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Pre-ranking fuse thrash
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.stages.low_conf_fuse_stages.run_connector_fuse_pass_pre_ranking`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-full_master_ranking — stage `full_master_ranking`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_full_master_ranking`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["full_master_ranking"]` → `selection.run_full_master_ranking` → artifact writers → `.stage_done/full_master_ranking`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `master/selection.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Ranking authority vs selection/air fights
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `selection.run_full_master_ranking`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `heal-navigate-pins`
- Status: OPEN_RISK

### STG-selection_order_sanitize — stage `selection_order_sanitize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_selection_order_sanitize`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["selection_order_sanitize"]` → `interview_mux.artifact_sanitize.selection.run_selection_order_sanitize` → artifact writers → `.stage_done/selection_order_sanitize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Has incompleteness; residual callsite
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L1 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.artifact_sanitize.selection.run_selection_order_sanitize`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `stage-completion-callsite-audit`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-air_script_compose — stage `air_script_compose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_air_script_compose`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["air_script_compose"]` → `interview_mux.air_script.run_air_script_compose` → artifact writers → `.stage_done/air_script_compose`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `mastering/mastering_plan.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Air script compose without incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.air_script.run_air_script_compose`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `air-order-policy`
- Status: OPEN_RISK

### STG-nugget_corpus_mine — stage `nugget_corpus_mine`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_nugget_corpus_mine`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["nugget_corpus_mine"]` → `analysis_extended.run_nugget_corpus_mine` → artifact writers → `.stage_done/nugget_corpus_mine`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/nugget_corpus.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Nugget mine hollow
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `analysis_extended.run_nugget_corpus_mine`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-information_package_plan — stage `information_package_plan`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_information_package_plan`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["information_package_plan"]` → `interview_mux.information_packages.run_information_package_plan` → artifact writers → `.stage_done/information_package_plan`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Info packages thin
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.information_packages.run_information_package_plan`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-nugget_layup_compose — stage `nugget_layup_compose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_nugget_layup_compose`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["nugget_layup_compose"]` → `analysis_extended.run_nugget_layup_compose` → artifact writers → `.stage_done/nugget_layup_compose`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/nugget_layup_plan.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Incomplete-after-conductor risk
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `analysis_extended.run_nugget_layup_compose`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `layup-completeness`
- Status: OPEN_RISK

### STG-gap_report_sanitize — stage `gap_report_sanitize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_gap_report_sanitize`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["gap_report_sanitize"]` → `interview_mux.artifact_sanitize.gap_report.run_gap_report_sanitize` → artifact writers → `.stage_done/gap_report_sanitize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Has incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L1 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.artifact_sanitize.gap_report.run_gap_report_sanitize`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `stage-completion-callsite-audit`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-refinement_agenda — stage `refinement_agenda`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_refinement_agenda`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["refinement_agenda"]` → `run_refinement_agenda` → artifact writers → `.stage_done/refinement_agenda`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Refinement gate decide_pass; no LLM but thin agenda
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `run_refinement_agenda`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-gap_framing_recompose — stage `gap_framing_recompose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_gap_framing_recompose`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["gap_framing_recompose"]` → `run_gap_framing_recompose` → artifact writers → `.stage_done/gap_framing_recompose`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Recompose after sanitize may reintroduce thin VO
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `run_gap_framing_recompose`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `framing-shard`
- Status: OPEN_RISK

### STG-selection_framing_apply — stage `selection_framing_apply`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_selection_framing_apply`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["selection_framing_apply"]` → `run_selection_framing_apply` → artifact writers → `.stage_done/selection_framing_apply`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Apply framing to selection drift
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `run_selection_framing_apply`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-air_script_seams — stage `air_script_seams`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_air_script_seams`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["air_script_seams"]` → `interview_mux.air_script.run_air_script_seams` → artifact writers → `.stage_done/air_script_seams`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `mastering/mastering_plan.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Seam LLM retries / thrash
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.air_script.run_air_script_seams`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `llm-hard-stop-routing`
- Status: OPEN_RISK

### STG-air_contract_sanitize — stage `air_contract_sanitize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_air_contract_sanitize`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["air_contract_sanitize"]` → `interview_mux.artifact_sanitize.air_script.run_air_contract_sanitize` → artifact writers → `.stage_done/air_contract_sanitize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Has incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L1 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.artifact_sanitize.air_script.run_air_contract_sanitize`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `stage-completion-callsite-audit`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-transitions — stage `transitions`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_transitions`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["transitions"]` → `selection.run_transitions` → artifact writers → `.stage_done/transitions`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `master/transitions.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Transitions freeze vs remutate
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `selection.run_transitions`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `transitions-freeze`
- Status: OPEN_RISK

### STG-sound_design_plan — stage `sound_design_plan`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_sound_design_plan`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["sound_design_plan"]` → `sound_design_stages.run_sound_design_plan` → artifact writers → `.stage_done/sound_design_plan`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/sound_design_plan.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Has incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L1 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `sound_design_stages.run_sound_design_plan`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `stage-completion-callsite-audit`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-sound_design_vo_finalize — stage `sound_design_vo_finalize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_sound_design_vo_finalize`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["sound_design_vo_finalize"]` → `sound_design_vo_finalize.run_sound_design_vo_finalize` → artifact writers → `.stage_done/sound_design_vo_finalize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: VO finalize seats before synth
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `sound_design_vo_finalize.run_sound_design_vo_finalize`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `vo-seat-authority`
- Status: OPEN_RISK

### STG-vo_line_adjudicate — stage `vo_line_adjudicate`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_vo_line_adjudicate`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["vo_line_adjudicate"]` → `vo_line_adjudicate.run_vo_line_adjudicate` → artifact writers → `.stage_done/vo_line_adjudicate`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `understanding/vo_line_adjudication.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Adjudicate lines vs seats
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `vo_line_adjudicate.run_vo_line_adjudicate`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `vo-seat-authority`
- Status: OPEN_RISK

### STG-vo_synthesize — stage `vo_synthesize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_vo_synthesize`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["vo_synthesize"]` → `vo_synthesize.run_vo_synthesize` → artifact writers → `.stage_done/vo_synthesize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `mastering/vo_synthesize.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: local-ML — model-tool-calls.md
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Chatterbox/script↔WAV/G1 circular
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `vo_synthesize.run_vo_synthesize`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `vo-seat-authority`
- Status: OPEN_RISK

### STG-edl_narrative_audit — stage `edl_narrative_audit`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_edl_narrative_audit`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["edl_narrative_audit"]` → `edl_narrative_audit.run_edl_narrative_audit` → artifact writers → `.stage_done/edl_narrative_audit`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `master/edl_narrative_audit.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Narrative audit soft
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `edl_narrative_audit.run_edl_narrative_audit`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-edl — stage `edl`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_edl`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["edl"]` → `assembly.run_edl` → artifact writers → `.stage_done/edl`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `master/edl.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: EDL leads master; remutate chains
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `assembly.run_edl`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `committed-master-honesty`
- Status: OPEN_RISK

### STG-assembly_preview — stage `assembly_preview`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_assembly_preview`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["assembly_preview"]` → `assembly.run_preview` → artifact writers → `.stage_done/assembly_preview`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `master/assembly_preview.wav`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Preview vs committed mix mismatch
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `assembly.run_preview`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-listen_delight_audit — stage `listen_delight_audit`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_listen_delight_audit`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["listen_delight_audit"]` → `interview_mux.listen_delight.run_listen_delight_audit` → artifact writers → `.stage_done/listen_delight_audit`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `mastering/listen_delight_audit.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Full-auto unattended waiver soft-seal
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L3 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.listen_delight.run_listen_delight_audit`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `delight-authoritative`
- Status: OPEN_RISK

### STG-music_palette_compose — stage `music_palette_compose`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_music_palette_compose`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["music_palette_compose"]` → `interview_mux.stages.music_palette_compose.run_music_palette_compose` → artifact writers → `.stage_done/music_palette_compose`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `sound_design/music_palette_compose.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: MusicGen + mix_epoch deferral
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.stages.music_palette_compose.run_music_palette_compose`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `music-epoch`
- Status: OPEN_RISK

### STG-sfx_prompt_craft — stage `sfx_prompt_craft`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_sfx_prompt_craft`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["sfx_prompt_craft"]` → `sound_design_stages.run_sfx_prompt_craft` → artifact writers → `.stage_done/sfx_prompt_craft`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `sound_design/sfx_prompts.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: Has incompleteness
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L1 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `sound_design_stages.run_sfx_prompt_craft`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `stage-completion-callsite-audit`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-mmaudio_sfx — stage `mmaudio_sfx`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mmaudio_sfx`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["mmaudio_sfx"]` → `sfx_mmaudio.run_sfx_generation` → artifact writers → `.stage_done/mmaudio_sfx`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `sound_design/mmaudio_qa.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: local-ML — model-tool-calls.md
- Invariant: flushed honest artifacts before mark_done; incompleteness=yes
- Why weak: MMAudio local stack
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `sfx_mmaudio.run_sfx_generation`; `stage_completion.stage_artifact_incompleteness` hit=yes
- Suggested fix-cluster: `music-epoch`
- Status: OPEN_RISK

### STG-mix — stage `mix`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_mix`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["mix"]` → `assembly.run_mix` → artifact writers → `.stage_done/mix`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `master/assembly.wav`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: mix_epoch_block can no-op when Phase A unsealed
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `assembly.run_mix`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `music-epoch`
- Status: OPEN_RISK

### STG-junction_snip_qa — stage `junction_snip_qa`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_junction_snip_qa`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["junction_snip_qa"]` → `interview_mux.junction_snip_qa.run_junction_snip_qa` → artifact writers → `.stage_done/junction_snip_qa`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `master/seam_autopsy.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Remaster budget / heal thrash
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.junction_snip_qa.run_junction_snip_qa`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `junction-remaster`
- Status: OPEN_RISK

### STG-master_finalize — stage `master_finalize`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_master_finalize`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["master_finalize"]` → `mastering.run_master_finalize` → artifact writers → `.stage_done/master_finalize`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `master/master.wav`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Commitment vs bare artifact_exists
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S3
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `mastering.run_master_finalize`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `committed-master-honesty`
- Status: OPEN_RISK

### STG-master_transcript_build — stage `master_transcript_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_master_transcript_build`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["master_transcript_build"]` → `interview_mux.asset_transcripts.run_master_transcript_build` → artifact writers → `.stage_done/master_transcript_build`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `master/transcript.json`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Feeds G-Publish; hollow transcript
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `interview_mux.asset_transcripts.run_master_transcript_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-episode_meta_build — stage `episode_meta_build`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_episode_meta_build`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["episode_meta_build"]` → `podcast_publish.run_episode_meta_build` → artifact writers → `.stage_done/episode_meta_build`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Meta LLM/ship
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `podcast_publish.run_episode_meta_build`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### STG-episode_cover_prompt_craft — stage `episode_cover_prompt_craft`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_episode_cover_prompt_craft`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["episode_cover_prompt_craft"]` → `podcast_publish.run_episode_cover_prompt_craft` → artifact writers → `.stage_done/episode_cover_prompt_craft`
- Prompt / schema / artifact: LLM — see prompt-schema-mismatch.md / docs/prompts/; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: llm_simple / homunculus loop
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Cover prompt craft
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `podcast_publish.run_episode_cover_prompt_craft`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `prompt-schema-registry`
- Status: OPEN_RISK

### STG-podcast_encode_mp3 — stage `podcast_encode_mp3`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_podcast_encode_mp3`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["podcast_encode_mp3"]` → `podcast_publish.run_podcast_encode_mp3` → artifact writers → `.stage_done/podcast_encode_mp3`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Encode from uncommitted master risk
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `podcast_publish.run_podcast_encode_mp3`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `committed-master-honesty`
- Status: OPEN_RISK

### STG-episode_cover_generate — stage `episode_cover_generate`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_episode_cover_generate`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["episode_cover_generate"]` → `podcast_publish.run_episode_cover_generate` → artifact writers → `.stage_done/episode_cover_generate`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Cover cascade vision pick
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `podcast_publish.run_episode_cover_generate`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `prompt-schema-registry`
- Status: OPEN_RISK

### STG-podcast_publish — stage `podcast_publish`
- Surface: stage
- Modes affected: Manual | Full-auto | Partial
- Brain: 0.1.0 (seed walk + conductor `run_stage_podcast_publish`)
- Call graph: `dispatch_stage` → `pipeline._delivery_stage_fns["podcast_publish"]` → `podcast_publish.run_podcast_publish` → artifact writers → `.stage_done/podcast_publish`
- Prompt / schema / artifact: N/A deterministic or local-ML; primary≈ `see STAGE_ARTIFACT_DISK_PATHS / writers in impl`
- Expected output: schema under `docs/cross-cutting/json-schemas/` when LLM; else writers in impl module
- Model or tool invoke: N/A
- Invariant: flushed honest artifacts before mark_done; incompleteness=**NO**
- Why weak: Partial never auto-upload; consent honesty
- Manifestation: GUI stageIncompleteReason; seed-order errors; consumer StageError; soft-gate false-green
- Intended heal/stop: recovery_controller / incompleteness_resume_stage / identical×3 halt
- Operator footgun: Manual Run-from-stage on consumer; Partial overlay ignore; Full-auto auto-gate past weak upstream
- Likelihood: L2 | Severity: S2
- Evidence: `src/interview_mux/pipeline.py` _delivery_stage_fns; `podcast_publish.run_podcast_publish`; `stage_completion.stage_artifact_incompleteness` hit=no
- Suggested fix-cluster: `g-publish-consent`
- Status: OPEN_RISK


---

## High-risk delivery depth cards (call-graph)

### STG-vo_synthesize-DEPTH — script↔WAV + pending + G1

- Surface: stage
- Modes: Manual | Full-auto | Partial
- Call graph: vo_synthesize → Chatterbox; vo_synthesis_audit bind; stage_completion incompleteness; may_rewind_to_vo_synthesize; write_staging pending WAVs
- Invariant: seated scripts match WAV hashes; G1 green seals adjudicate
- Why weak: pending-only WAVs; circular g1 resume; clamp missing on some omit paths
- Likelihood: L3 | Severity: S4
- Evidence: stage_completion vo_synthesize; vo_synthesis_audit; delivery_invariants
- Fix-cluster: `vo-seat-authority`
- Status: OPEN_RISK

### STG-transitions-DEPTH — pair freeze + stale consumers

- Surface: stage
- Modes: all
- Call graph: transitions LLM → pair freeze JSON; STALE consumers include edl; may_rewind deferred pairs
- Invariant: frozen pairs do not unmark full vo_synthesize; edl sees stale transitions
- Why weak: mid-delivery pair expansion; sticky Run Transitions CTA
- Likelihood: L2 | Severity: S4
- Evidence: transition_vo freeze helpers; delivery_guardrails may_rewind
- Fix-cluster: `transitions-freeze`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-nugget_layup-DEPTH — incomplete-after-conductor / hollow layup

- Surface: stage
- Modes: Full-auto | Partial
- Call graph: nugget_layup_compose LLM → gap_report authority; incompleteness; heal routing layup_stale
- Why weak: conductor marks progress while layup incomplete; stale routed to wrong resume
- Likelihood: L3 | Severity: S3
- Evidence: stage_completion nugget_layup_compose; heal_routing
- Fix-cluster: `layup-completeness`
- Status: OPEN_RISK

### STG-mix-DEPTH — safe_mix_resume + music epoch

- Surface: stage
- Modes: all
- Call graph: filter_delivery_candidates; safe_mix_resume_stage; premature_cap; ensure_mmaudio_qa_before_mix
- Why weak: mix scheduled while music incomplete; wrong pin to narrative
- Likelihood: L2 | Severity: S4
- Evidence: delivery_guardrails music_epoch_complete; delivery_recovery
- Fix-cluster: `music-epoch`
- Status: LIKELY_MITIGATED_ON_HEAD

### STG-junction-DEPTH — remaster + ship_path

- Surface: stage
- Modes: all
- Call graph: junction_snip_qa budgeted remaster; ship_path_ready; G-Listen re-arm
- Why weak: oscillation; pending master lie; soft residuals
- Likelihood: L2 | Severity: S4
- Evidence: junction_snip_qa; ship_path_ready
- Fix-cluster: `junction-remaster`
- Status: OPEN_RISK

### STG-master_finalize-DEPTH — ledger/seam producer pin

- Surface: stage
- Modes: all
- Call graph: finalize_input_producer_pin; assembly_ledger; seam_autopsy; committed_master_wav
- Why weak: missing ledger pins wrong stage; pending master.wav
- Likelihood: L2 | Severity: S3
- Evidence: delivery_guardrails finalize pins; delivery_invariants.committed_master_wav
- Fix-cluster: `finalize-input-pins`
- Status: OPEN_RISK

### STG-listen_delight-DEPTH — remutate chain

- Surface: stage
- Modes: Full-auto | Partial | Manual
- Call graph: listen_delight_audit → remutate plan → active_remutate_stages → seams/EDL
- Why weak: mix-only remutate noop; budget exhaust soft-green
- Likelihood: L2 | Severity: S3
- Evidence: listen_delight modules; REMUTATE_PLAN_RELS
- Fix-cluster: `remutate-chain`
- Status: OPEN_RISK

### STG-podcast_publish-DEPTH — Partial never auto S3

- Surface: stage
- Modes: Partial vs Full-auto
- Call graph: podcast_publish → G-Publish consent; sync scripts
- Why weak: Prepare confused with upload; advisories
- Likelihood: L2 | Severity: S2
- Evidence: automation_run partial; GPublishPanel
- Fix-cluster: `g-publish-consent`
- Status: OPEN_RISK


---

## Delivery DEEP enrichment (rank→EDL)

# DELIVERY STG-*-DEEP cards (HEAD identify-only)

Brain **0.1.0**. No product edits. No `ASSETS/executions/`. Scoring: L1–L3 / S1–S4 per catalog INDEX.

---

### STG-topic_coverage_audit-DEEP — soft coverage authority before ranking
- **Surface:** stage (`plan_rank`)
- **Modes:** Manual | Full-auto | Partial
- **Call graph:** `dispatch_stage` → `pipeline._delivery_stage_fns` → `analysis_extended.run_topic_coverage` → optional `coherence.maybe_run_coherence_analysis` → `talking_points_authority.try_deterministic_coverage` **or** `run_flow_llm_stage` → `write_validated_artifact`/`make_stage_persist` → `master/coverage_audit.json` → `maybe_run_post_stage_specialists` → optional post_coverage coherence → `.stage_done`
- **Prompts/tools:** `selection/topic-coverage-audit.system.txt` (+ `.tbiy`); arbiter `topic_coverage_audit.json`; schema `coverage_audit_artifact`; OpenAI via `llm_simple` (max 2). Deterministic path when talking-points authority on — **no LLM**.
- **Why weak:** No `stage_artifact_incompleteness` branch. Deterministic path can mark done with authority-derived score while LLM path’s `missing_coverage` is advisory to ranking. Soft audit → hollow ranking membership.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `hollow-done-coverage`
- **Evidence:** `stages/analysis_extended.py:run_topic_coverage`; `stage_completion` hit=no; `prompt-schema-mismatch` OF-01

---

### STG-narrative_arc_plan-DEEP — chapter plan vs federated air-order
- **Surface:** stage
- **Modes:** all
- **Call graph:** → `run_narrative_arc` → `try_deterministic_narrative` **or** LLM → `enrich_narrative_plan_for_persist` → `master/narrative_plan.json` → hitch/ranking consumers
- **Prompts/tools:** `selection/narrative-arc-plan.system.txt`; arbiter `narrative_arc_plan.json`; OF-02 schema. Deterministic when talking-points authority on.
- **Why weak:** No incompleteness. Chapters become topo constraints for ranking/hitch, but air-script Pass A / shape `ordered_segment_ids` / selection finalize can re-federate order — arc looks authoritative while air drifts.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `air-order-policy` / `hollow-done-coverage`
- **Evidence:** `analysis_extended.run_narrative_arc`; `selection.finalize_selection_order` reads narrative_plan; hitch requires narrative/intent

---

### STG-chapter_close_hitch-DEEP — one-shot wipe + inner walk remap
- **Surface:** process stage (non-LLM)
- **Modes:** all
- **Call graph:** → `chapter_close_hitch.run_chapter_close_hitch` → latch short-circuit / disabled / no-plan skip → snapshot keepers → `compute_recut_windows` + acoustic refine → remap → **`ctx.clear_from("boundary_detection", ANALYSIS+DELIVERY)`** → rewrite refs / rebind VO / omit remap → `run_inner_walk` → post-walk patches → latch committed → mark_done
- **Prompts/tools:** none (process). Artifacts: latch/remap/keepers/intent under mastering + boundaries.
- **Why weak:** Nuclear clear_from mid-delivery; resume/listen_restage paths; no incompleteness beyond latch. Inner walk can thrash seed front; VO/omit remaps fight later seat authority.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `invalidation-blast` / hitch-budget
- **Evidence:** `chapter_close_hitch.py:run_chapter_close_hitch` (~1477+); `PRODUCER_PIN_TABLE["chapter_close_hitch"]`; incompleteness hit=no

---

### STG-connector_fuse_pass_pre_ranking-DEEP — second economy seam fuse
- **Surface:** stage (LLM economy)
- **Modes:** all
- **Call graph:** → `low_conf_fuse_stages.run_connector_fuse_pass_pre_ranking` → `run_connector_fuse_pass(pass_id="pre_ranking")` → `segment_fuse.run_connector_fuse_pass` → economy `run_prompt_envelope` batches → fuse rewrite → rounds JSON
- **Prompts/tools:** `segmentation/connector-seam-adjudicate.system.txt`; tier economy→standard→flagship fallback in fuse cfg.
- **Why weak:** Second fuse after analysis fuse; can mutate boundaries/manifest immediately before ranking without incompleteness. Disabled = silent skip. Junction_heal can force re-adjudicate later → thrash.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `llm-hard-stop-routing` / fuse-idempotency
- **Evidence:** `low_conf_fuse_stages.py:113–115`; `segment_fuse.SEAM_PROMPT_REL`; port-manifest “Second seam fuse before ranking”

---

### STG-full_master_ranking-DEEP — selection authority + multi-candidate finalize
- **Surface:** stage (LLM + heavy post)
- **Modes:** all
- **Call graph:** → `selection.run_full_master_ranking` → `check_narrative_qc` → `run_flow_llm_stage` → persist: topo repair → NLE overlay → auto_pack → creative/framing/hard_keep/STT guards → candidate pick (ranking vs chapters vs shape) → hook early → `finalize_selection_order` / `commit_selection_mutation` → story_health / integrity block → post specialists
- **Prompts/tools:** `selection/full-master-ranking.system.txt`; OF-03; NLE as input overlay tool.
- **Why weak:** Many post-LLM mutators rewrite LLM order; critical integrity/`story_health=fail` can hard-block; no dedicated incompleteness branch (persistable gate only). Downstream air-script/sanitize/hitch re-mutate — ranking “done” ≠ locked air.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `heal-navigate-pins` / `air-order-policy`
- **Evidence:** `stages/selection.py:run_full_master_ranking`; `finalize_selection_order`; incompleteness hit=no

---

### STG-selection_order_sanitize-DEEP — non-amplifying selection scrub
- **Surface:** sanitize stage
- **Modes:** all
- **Call graph:** → `artifact_sanitize.selection.run_selection_order_sanitize` → `sanitize_master_selection` (fragment depth, overlap families, ordered↔excluded) → audit → commit via air-order boundary when actions
- **Prompts/tools:** none
- **Why weak:** Has incompleteness (good). Residual: re-entered from layup/framing/SDP consumers; refuse vs heal can pin wrong producer; fragment-depth rules interact with hitch remaps.
- **L/S:** L1 / S2
- **Status:** LIKELY_MITIGATED_ON_HEAD
- **Fix-cluster:** `stage-completion-callsite-audit`
- **Evidence:** `artifact_sanitize/selection.py:run_selection_order_sanitize`; `stage_completion` selection_order_sanitize branch

---

### STG-air_script_compose-DEEP — Pass A membership/omits (fail-open)
- **Surface:** non-LLM
- **Modes:** all
- **Call graph:** → `air_script.run_air_script_compose` → if enabled: `compose_pass_a` → circumstance card + spine + padding omits → write `mastering_plan.air_script` → optionally `enforce_air_script_omits` on selection + omit_ledger; **fail_open default**
- **Prompts/tools:** none
- **Why weak:** No incompleteness; fail-open swallows compose errors → hollow air_script while stage can still progress. Pass A omits mutate selection before nugget mine — authority fight with ranking finalize.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `air-order-policy` / `vo-seat-authority`
- **Evidence:** `air_script.py:1550–1559`; `PRODUCER_PIN_TABLE air_script_incomplete`; incompleteness hit=no

---

### STG-nugget_corpus_mine-DEEP — full-tape mine after ranking
- **Surface:** LLM
- **Modes:** all
- **Call graph:** → `run_nugget_corpus_mine` → if disabled: empty corpus + force mark_done → else `run_flow_llm_stage` + `strip_never_touch_nuggets` → `understanding/nugget_corpus.json`
- **Prompts/tools:** `nugget_layup/nugget-corpus-mine.system.txt`; OF-03a
- **Why weak:** Disabled path hollow-dones empty corpus; no incompleteness on thin/empty mines; packages/layup consume corpus under `require_corpus` — silent empty → package reject cascade.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `hollow-done-coverage` / `layup-completeness`
- **Evidence:** `analysis_extended.run_nugget_corpus_mine`; producer pin `nugget_corpus_mine`

---

### STG-information_package_plan-DEEP — high-bar packages (often shadow)
- **Surface:** non-LLM scorer
- **Modes:** all
- **Call graph:** → `information_packages.run_information_package_plan` → `build_candidates`/`select_commits` → candidates JSON → `patch_mastering_plan` (shadow vs commit modes) → audit + episode_close
- **Prompts/tools:** none
- **Why weak:** Default/shadow modes write empty `information_packages` on plan while audit still “succeeds”; no incompleteness; Pass B montage keys off packages that never bind air.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `hollow-done-coverage`
- **Evidence:** `information_packages.py:412–473`; `packages_affect_air` / mode shadow

---

### STG-nugget_layup_compose-DEEP — authoritative gap VO publisher
- **Surface:** LLM (+ QC regenerate)
- **Modes:** all (Full-auto/Partial amplify)
- **Call graph:** → CTA settle → may re-run `selection_order_sanitize` → batched `run_flow_llm_stage` → persist: heal/spoken-copy/freshness → `publish_layup_plan_to_gap_report` → QC → optional StageError degraded regenerate → incompleteness resume
- **Prompts/tools:** `nugget_layup/nugget-layup-compose.system.txt`; OF-03b
- **Why weak:** Owns gap_report before sanitize/recompose; incompleteness yes but conductor can advance while layup unsanitary/stale; QC invent/canned paths + materialize-over-skip fight seats.
- **L/S:** L3 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `layup-completeness`
- **Evidence:** `analysis_extended.run_nugget_layup_compose`; `stage_completion` nugget_layup_compose; catalog DEPTH sibling

---

### STG-gap_report_sanitize-DEEP — W1 shape sanitize (no seat authority)
- **Surface:** sanitize
- **Modes:** all
- **Call graph:** → `artifact_sanitize.gap_report.run_gap_report_sanitize` → dedupe/rebase/scaffolding strip/opening grammar/lock stamp — **explicitly not** seat/omit (W3 owns that)
- **Prompts/tools:** none
- **Why weak:** Incompleteness present. Can strip scaffolding / rebases after layup publish; if W1 mutates text hashes, later VO bind / adjudicate see drift. Authority split vs air_contract is correct but easy to mis-heal.
- **L/S:** L1 / S2
- **Status:** LIKELY_MITIGATED_ON_HEAD
- **Fix-cluster:** `stage-completion-callsite-audit` / `vo-seat-authority`
- **Evidence:** `gap_report.py` module docstring W1; `stage_completion` gap_report_sanitize

---

### STG-refinement_agenda-DEEP — L0 eligible-class compiler (no LLM)
- **Surface:** non-LLM
- **Modes:** all
- **Call graph:** → `refinement_agenda.run_refinement_agenda(phase="confirm")` → tape character + policy pack ± priors → write `understanding/refinement_agenda.json` → ledger → force mark_done
- **Prompts/tools:** none (priors/policy tables)
- **Why weak:** No incompleteness; simple_tape_override empties eligible; decide_pass downstream may skip real recomposes while agenda looks “confirmed.”
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `hollow-done-coverage`
- **Evidence:** `refinement_agenda.py:26–115`; pipeline comment “No LLM — gated by refinement_gate.decide_pass”

---

### STG-gap_framing_recompose-DEEP — Pass2 or layup thin adapter
- **Surface:** non-LLM refinement
- **Modes:** all
- **Call graph:** if nugget_layup authoritative → republish layups + mark done; else `decide_pass` → skip-copy **or** sharded deterministic keep/drop + prior-context courtesy rewrite → repair_gap_report → orientation → write final gap
- **Prompts/tools:** none (deterministic; not gap compose LLM)
- **Why weak:** When layup authoritative, stage is no-op theater; when activate, can drop non-kept lines / rewrite openers — fights sanitize stamps; no incompleteness.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `framing-shard` / `layup-completeness`
- **Evidence:** `refinement_passes.run_gap_framing_recompose`

---

### STG-selection_framing_apply-DEEP — framing excludes + gap rebase
- **Surface:** non-LLM
- **Modes:** all
- **Call graph:** → `decide_pass` → exclude segments covered by framing VO → validate_framing_ranking → rebase/drop/clone-adjacency/orientation/restore_layup on gap → post `sanitize_master_selection` commit
- **Prompts/tools:** none
- **Why weak:** Mutates selection after ranking/air Pass A; restore_layup can reintroduce lines sanitize just cleaned; no incompleteness; hard framing issues can skip write silently.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `air-order-policy` / `invalidation-blast`
- **Evidence:** `refinement_passes.run_selection_framing_apply`

---

### STG-air_script_seams-DEEP — Pass B seats + sonic hunt (fail-open)
- **Surface:** non-LLM (despite shallow “Seam LLM” label)
- **Modes:** all
- **Call graph:** → `run_air_script_seams` → `compose_pass_b` (montage moves / vo_seats) → `persist_air_script_omits_on_gap_report` → `attach_sonic_scenes` → `vo_contract.sync_vo_contract_after_layup` (raise on drift) → **fail_open default**
- **Prompts/tools:** none
- **Why weak:** Seat authority set here but fail-open can drop seat sync; no incompleteness; seed-prereq / stale consumers fight transitions (catalog W7). Heuristic montage (music_face_out vs vo_then_clip) under/over-seats.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `vo-seat-authority` / `air-order-policy`
- **Evidence:** `air_script.py:1562–1578`; producer pin `air_script_seams`; delivery_thrash W7 seams honesty

---

### STG-air_contract_sanitize-DEEP — sole seats↔gap↔omit scrub (W3)
- **Surface:** sanitize
- **Modes:** all
- **Call graph:** → `artifact_sanitize.air_script.run_air_contract_sanitize` → `sanitize_air_contract` (dedupe seated/omitted, gap flags, omit ledger) → write plan/gap/omit
- **Prompts/tools:** none
- **Why weak:** Incompleteness yes. Still multi-writer ecosystem (seams/hitch/driver heals) can re-dirty contract after mark_done; refuse paths escalate to needs_operator.
- **L/S:** L1 / S2
- **Status:** LIKELY_MITIGATED_ON_HEAD
- **Fix-cluster:** `vo-seat-authority` / `stage-completion-callsite-audit`
- **Evidence:** `air_script.py` W3 docstring; `stage_completion` air_contract_sanitize

---

### STG-transitions-DEEP — adjacency LLM + prune + optional pair freeze
- **Surface:** LLM
- **Modes:** all
- **Call graph:** prerepair selection (opening adjacency / integrity / reconcile) → `run_synthetic_framing_plan` → `run_flow_llm_stage` → persist_with_framing_dedupe (reverse-jump prune, spoken_copy_guard, VO identity stamp) → optional `stamp_transitions_pair_freeze` if G1 skipped/open
- **Prompts/tools:** `assembly/transitions.system.txt`; arbiter `transitions.json`; OF-04. `llm_simple` can persist partial/empty to unblock SDP.
- **Why weak:** Selection mutation from transitions producer; pair freeze vs remutate; stale transitions block edl (mitigated on HEAD per DEPTH). Empty persist soft-greens. No general incompleteness (only via consumers).
- **L/S:** L2 / S3
- **Status:** OPEN_RISK (freeze path LIKELY_MITIGATED)
- **Fix-cluster:** `transitions-freeze`
- **Evidence:** `selection.run_transitions`; `llm_simple` transitions persist notes; catalog STG-transitions-DEPTH

---

### STG-sound_design_plan-DEEP — Flow1 SDP LLM with reconcile preflight
- **Surface:** LLM
- **Modes:** all
- **Call graph:** enabled gate → fail-open `order_reconcile` / soundscape / episode_structure refresh → LLM → merge assets/flow_plans/motif → placeholder cues (real placement later in music_palette_compose) → validate → incompleteness checks sanitary+SDP written
- **Prompts/tools:** `sound_design/plan-flow1.system.txt`; OF-05
- **Why weak:** Placeholder cues ≠ audible plan; order_reconcile fail-open; incompleteness can loop on selection/layup unsanitary; disabled marks skipped done.
- **L/S:** L1–L2 / S2
- **Status:** LIKELY_MITIGATED_ON_HEAD (incompleteness) / OPEN_RISK (placeholder honesty)
- **Fix-cluster:** `stage-completion-callsite-audit` / music-epoch upstream
- **Evidence:** `sound_design_stages.run_sound_design_plan`; `stage_completion` sound_design_plan

---

### STG-sound_design_vo_finalize-DEEP — measure VO bridges (often pre-synth)
- **Surface:** non-LLM
- **Modes:** all
- **Call graph:** opening adjacency repairs → load SDP cues → measure `vo_pickup` WAVs → stamp durations/rolls → validate (on fail: leave SDP, still mark_done) → patch sonic_context → **direct `ctx.mark_done`**
- **Prompts/tools:** none (wav duration)
- **Why weak:** Runs **before** `vo_line_adjudicate`/`vo_synthesize` in DELIVERY_ORDER — often skips (no WAV) yet marks done; validation failure still marks done; mutates selection via adjacency helpers.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `vo-seat-authority`
- **Evidence:** `v2/config.py` order; `sound_design_vo_finalize.py:16–116`

---

### STG-vo_line_adjudicate-DEEP — per-line economy adjudicate + intro (0.1.0)
- **Surface:** LLM (homunculus 0.1.0+)
- **Modes:** all
- **Call graph:** omit-ledger stamp → body lines needing adjudicate → `run_adjudicate_batches` (`run_flow_llm_stage` + `vo/vo-line-adjudicate.system.txt`) → apply → intro compose → allocation plan → nugget air coverage (fail-open cfg or loud_fail) → mark_done; may nuke synth WAVs on text change
- **Prompts/tools:** `vo/vo-line-adjudicate.system.txt`; intro compose prompt; OF-06a
- **Why weak:** No incompleteness branch; fail-open coverage soft-greens; text changes nuke WAVs → vo_synthesize thrash; seats from seams may not match adjudicated scripts.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `vo-seat-authority`
- **Evidence:** `vo_line_adjudicate.run_vo_line_adjudicate_stage`; delivery_thrash adjudicate skip/fresh WAV notes

---

### STG-vo_synthesize-DEEP — Chatterbox/local synth + seat assert
- **Surface:** local-ML / process
- **Modes:** all (monotonic rules after assembly)
- **Call graph:** `synthesize_spoken_transitions` (fail-open) → `resync_required_synthesize_wavs` → restamp EDL paths → promote staged `master/transitions/` → `persist_vo_pair_gap` → `assert_seated_vo_rendered`; incompleteness via pairs + sanitary + VO audit
- **Prompts/tools:** local S2S/Chatterbox (ASSETS venv) — not OpenAI
- **Why weak:** Transition fail-open + pair freeze interactions; G1/seat circular; pending WAV shadows; can defer-done while GUI shows incomplete; highest thrash surface.
- **L/S:** L3 / S4
- **Status:** OPEN_RISK
- **Fix-cluster:** `vo-seat-authority` / `monotonic-vo`
- **Evidence:** `stages/vo_synthesize.py`; `stage_completion` vo_synthesize + defer_done; catalog DEPTH

---

### STG-edl_narrative_audit-DEEP — heard-WAV-flow LLM before EDL
- **Surface:** LLM
- **Modes:** all
- **Call graph:** → compact vo_coverage + air seats → `run_flow_llm_stage` → `maybe_repair_after_narrative_audit` → `master/edl_narrative_audit.json`
- **Prompts/tools:** `selection/edl-narrative-audit.system.txt`; OF-06
- **Why weak:** No incompleteness; audit_mode claims heard WAV flow but nle_edits empty expected pre-edl; soft issues demoted by artifact_repairs; `verdict=fail` hard-stops edl — soft false fail/pass both hurt.
- **L/S:** L2 / S2
- **Status:** OPEN_RISK
- **Fix-cluster:** `hollow-done-coverage` / audit-repair honesty
- **Evidence:** `edl_narrative_audit.run_edl_narrative_audit`; `assembly.run_edl` fail exit; artifact_repairs demote notes

---

### STG-edl-DEEP — timeline construction from air + VO
- **Surface:** non-LLM build
- **Modes:** all
- **Call graph:** refuse if narrative audit fail → QC → NLE heal/apply → air_script omit bind → gap repair/orientation → build EDL events (speech/VO/transitions) → write `master/edl.json`; incompleteness if seated VO paths missing
- **Prompts/tools:** none
- **Why weak:** Shallow card said incompleteness=NO — **HEAD has seated-VO incompleteness**. Still remutate/heal chains; selection writes from edl path; producer-pin gravity for hollow_done/seed_order.
- **L/S:** L2 / S3
- **Status:** OPEN_RISK
- **Fix-cluster:** `committed-master-honesty` / `vo-seat-authority`
- **Evidence:** `assembly.run_edl`; `stage_completion` `stage_id == "edl"` seated VO check; PRODUCER_PIN_TABLE defaults to edl

---

## Cross-note (this band)

| Pattern | Stages |
|---|---|
| Fail-open hollow progress | air_script_compose/seams, connector fuse skip, info packages shadow, vo_synth transition fail-open |
| No incompleteness | coverage, arc, hitch, fuse, ranking, air compose/seams, corpus, packages, agenda, recompose, framing_apply, transitions*, vo_finalize, adjudicate, edl_narrative |
| Has incompleteness | selection_order_sanitize, gap_report_sanitize, air_contract_sanitize, nugget_layup, sound_design_plan, vo_synthesize, **edl** |
| Real OpenAI | coverage†, arc†, fuse, ranking, corpus, layup, transitions, SDP, adjudicate, edl_narrative († unless talking_points_authority deterministic) |
| Local-ML | vo_synthesize |


---

## Mix-Ship DEEP enrichment

# DELIVERY/SHIP stage deep cards (HEAD identify-only)

Catalog: `DELIVERY_ORDER` in `src/interview_mux/v2/config.py` includes all 14 stages below. Dispatch: `src/interview_mux/pipeline.py` `_stage_handlers`.

---

### STG-assembly_preview-DEEP — speech+VO preview (no SFX)
- **Surface:** stage | local-audio (ffmpeg + pydub)
- **Modes:** Manual | Full-auto | Partial (preview listen gate before SFX spend)
- **Brain:** 0.1.0 (same handler)
- **Call graph:** `pipeline` → `assembly.run_preview` → heal VO via `heal_vo_pickup_clip_source` → optional `write_committed_json(master/edl.json)` → ffmpeg slice speech/silence/VO → `concat_clips_with_crossfade` → `master/assembly_preview.wav` → `mark_done`
- **Local-ML / OpenAI:** none
- **Prompt / schema / artifact:** N/A LLM · primary out `master/assembly_preview.wav` (`prompt_validation.STAGE_ARTIFACT_PATHS`) · **does not write** `master/assembly_preview_meta.json` (still read by palette compose)
- **Why weak:** empty `transition` seats are **skipped** (mix last-chance synths later) → preview can green without aired transitions; `SystemExit` if no clips; EDL heal write can fail open (warning only)
- **L/S:** L2 | S2
- **Status:** OPEN_RISK
- **fix-cluster:** `preview-vs-mix-parity`
- **Evidence:** `stages/assembly.py:run_preview` · `stage_input_checks._check_assembly_preview` · `tests/test_assembly_vo_source_heal.py`

---

### STG-listen_delight_audit-DEEP — heuristic ship-floor audit (pre-mix)
- **Surface:** stage | cross-cut (remutate / PMQ)
- **Modes:** Manual (operator G-Listen) | Full-auto (remutate / loud-fail if `fail_early`) | Partial
- **Brain:** 0.1.0 (+ `ingest_catch` issues)
- **Call graph:** `run_listen_delight_audit` → `evaluate_listen_delight` (dims: cut_integrity, conversation_fit, sonic_weave, …) → write `mastering/listen_delight_audit.json` + `run_meta.qc_summaries` → optional remutate / `raise_loud_failure` · also `rerun_listen_delight_after_mix` (non-blocking) · authoritative re-run inside `run_post_master_quality` → `run_authoritative_listen_delight_at_ship`
- **Local-ML / OpenAI:** none (pure heuristics)
- **Prompt / schema / artifact:** schema `mastering_listen_delight_audit.schema.json` · artifact `mastering/listen_delight_audit.json`
- **Why weak:** default `fail_early_at_audit_stage=False` → **pre-mix advisory**; soft defaults when downstream evidence missing; remutate can rewind producers (`listen_delight_remutate`); palette compose reads wrong keys (`score`/`overall_score`/`summary` vs writer `overall` + `notes[]`)
- **L/S:** L2 | S2 (false-green pre-mix); ship gate stronger at finalize
- **Status:** OPEN_RISK (pre-mix / packet) · ship path LIKELY_MITIGATED_ON_HEAD via PMQ
- **fix-cluster:** `listen-delight-authority-timing`
- **Evidence:** `listen_delight.py:run_listen_delight_audit` · `post_master_quality.run_post_master_quality` · `tests/test_listen_delight.py`

---

### STG-music_palette_compose-DEEP — place fixed palette into SDP cues
- **Surface:** stage | LLM
- **Modes:** all (gated by assembly audio incompleteness)
- **Brain:** 0.1.0
- **Call graph:** `run_music_palette_compose` → `run_flow_llm_stage` → `persist`: normalize cues / `_default_cues` fallback → rewrite `understanding/sound_design_plan.json` + `sound_design/music_palette_compose.json`
- **Local-ML / OpenAI:** OpenAI via `run_flow_llm_stage` (flow LLM path; not flagship-tagged in `model_registry`)
- **Prompt / schema / artifact:** `docs/prompts/sound_design/music-palette-compose.system.txt` · `music_palette_compose_artifact.schema.json` · outs above
- **Why weak:** LLM miss → silent `_default_cues`; invalid asset_ids discarded then fallback; **delight hints packet dead** (key mismatch); mutates SDP after preview so mix can diverge from what operator heard
- **L/S:** L2 | S2
- **Status:** OPEN_RISK
- **fix-cluster:** `palette-cue-authority`
- **Evidence:** `stages/music_palette_compose.py:run_music_palette_compose` · `tests/test_music_palette_compose.py` · `stage_completion` assembly-audio gate

---

### STG-sfx_prompt_craft-DEEP — MusicGen prompt craft
- **Surface:** stage | LLM | gate G1.5 prompt review
- **Modes:** Manual (approve) | Full-auto (`maybe_auto_approve_prompt_review`) | Partial
- **Brain:** 0.1.0
- **Call graph:** `run_sfx_prompt_craft` → `run_flow_llm_stage` → `_normalize_sfx_prompts` → `write_validated_artifact(sound_design/sfx_prompts.json)` (no merge_from_disk) → `maybe_auto_approve_prompt_review`
- **Local-ML / OpenAI:** OpenAI (`run_flow_llm_stage`; listed in `model_registry` mid-tier set)
- **Prompt / schema / artifact:** `docs/prompts/sound_design/sfx-prompt-craft.system.txt` (+ `.tbiy`) · `sfx_prompts_artifact.schema.json` · arbiter `docs/prompts/_shared/arbiter-rubrics/sfx_prompt_craft.json`
- **Why weak:** spend gate for `mmaudio_sfx` depends on approve; auto-approve can pass weak prompts; craft-before-listen ordering fights operator intent if seed jumps; skip when sound_design disabled still marks skipped
- **L/S:** L2 | S2
- **Status:** OPEN_RISK
- **fix-cluster:** `sfx-prompt-spend-gate`
- **Evidence:** `stages/sound_design_stages.py:run_sfx_prompt_craft` · `sfx_prompt_review.py` · `llm_flow_hardening` spend gate · `llm_preflight._preflight_sfx_prompt_craft`

---

### STG-mmaudio_sfx-DEEP — MusicGen ladder → MMAudio backup
- **Surface:** stage | local-ML
- **Modes:** all (post-listen / G1.5; Full-auto auto-refine)
- **Brain:** 0.1.0 (`run_mmaudio_host` tool also)
- **Call graph:** `sfx_mmaudio.run_sfx_generation` → `require_spend_artifacts_complete` + `require_sfx_generation` + G1.5 clear → per-asset `_generate_with_retry` → `musicgen_runner.generate_music_clip` (large→medium→small) → optional `mmaudio_runner.generate_text_to_audio` backup → `run_mmaudio_asset_qa` → `heal_mmaudio_qa_wav_parity` → `mark_done` · refine path `maybe_auto_refine` / `execute_fitness_remediation` → skip_cue
- **Local-ML / OpenAI:** **MusicGen** (`ASSETS/local_musicgen/venv`) · **MMAudio** (`ASSETS` isolated venv / `tools/mmaudio_generate.py`) · no OpenAI
- **Prompt / schema / artifact:** prompts from `sfx_prompts.json` · QA `sound_design/mmaudio_qa.json` (`mmaudio_qa.schema.json`) · WAVs under `sound_design/assets/`
- **Why weak:** stub/timeout ladders; best-of-N thrash; plan-hash skip can stale; fitness fail → `skip_cue` (hollow sonic_weave); incompleteness heal of empty QA; CPU medium prefer path
- **L/S:** L3 | S3
- **Status:** OPEN_RISK
- **fix-cluster:** `musicgen-mmaudio-spend-thrash`
- **Evidence:** `stages/sfx_mmaudio.py` · `musicgen_runner.py` ladder · `mmaudio_runner.py` · `tests/test_sfx_mmaudio*.py` · `tests/test_musicgen_realworld_ladder.py`

---

### STG-mix-DEEP — assembly.wav = speech+VO+SDP overlays
- **Surface:** stage | local-audio
- **Modes:** all (music-listen / publishability pre_mix)
- **Brain:** 0.1.0
- **Call graph:** `assembly.run_mix` → `require_spend_artifacts_complete` · `assert_consumer` · `checkpoint_publishability(pre_mix)` · `place_episode_close_cue` · `ensure_mmaudio_qa_before_mix` · ledger naked-seam assert · transition last-chance synth · `sound_design.mix` (pydub overlays, bed QC, placement QA) → `rerun_listen_delight_after_mix`
- **Local-ML / OpenAI:** none (may trigger local VO synth as last-chance)
- **Prompt / schema / artifact:** out `master/assembly.wav`
- **Why weak:** mutates live EDL (listenability / sanitize); missing overlays can hard-fail or leave gaps; VO pair gap persistence; post-mix delight non-blocking; heavy coupling to mmaudio QA restore
- **L/S:** L3 | S3
- **Status:** OPEN_RISK
- **fix-cluster:** `mix-edl-overlay-authority`
- **Evidence:** `stages/assembly.py:run_mix` · `sound_design.mix` · `tests/test_music_mix_and_gen.py` · delivery_thrash plan W1–W3

---

### STG-junction_snip_qa-DEEP — seam repair + remaster + feel LLM
- **Surface:** stage | LLM (+ deterministic detect/repair)
- **Modes:** advisory/blocking via `junction_snip` cfg; Full-auto remaster loops
- **Brain:** 0.1.0
- **Call graph:** `run_junction_snip_qa` → `detect_junction_findings` → `enrich_thought_complete_findings` (LLM optional after round≥2) → repair batch → `_budgeted_remaster_mix` → rescan · oscillation halt · `run_junction_feel_audit` (`run_prompt_envelope`) → directives · `_persist_terminal_autopsy` → `master/seam_autopsy.json` + `master/junction_snip_qa.json`
- **Local-ML / OpenAI:** OpenAI feel audit + thought-complete (`run_prompt_envelope`); remaster = mix path (local audio)
- **Prompt / schema / artifact:** feel/thought schemas in `prompt_validation` · required seed artifact `master/seam_autopsy.json` (QA also writes `junction_snip_qa.json`)
- **Why weak:** remaster budget exhaustion → `needs_operator` / loud-fail; oscillation; mode `off`/`missing_edl` still writes skip reports; LLM call ladder can escalate; finalize may re-invoke whole stage after optimizer
- **L/S:** L3 | S4
- **Status:** OPEN_RISK
- **fix-cluster:** `junction-remaster-thrash`
- **Evidence:** `junction_snip_qa.py:run_junction_snip_qa` · `tests/test_junction_snip_qa.py` · `stage_input_checks._check_junction_snip_qa`

---

### STG-master_finalize-DEEP — loudnorm → master.wav + PMQ
- **Surface:** stage | local-audio | ship gate
- **Modes:** all (G-Listen + timeline optimizer must clear)
- **Brain:** 0.1.0
- **Call graph:** `run_master_finalize` → layup/omit/VO sync heals → `require_timeline_optimizer_clear` / `require_g_listen_clear` → optional `take_best_candidate` → **re-run `run_junction_snip_qa`** → `master_wav` (ffmpeg two-pass loudnorm + alimiter) → `run_post_master_quality(block=True)` (re-runs authoritative listen delight) → `mark_g_publish_pending`
- **Local-ML / OpenAI:** none for render; PMQ may invoke OpenAI only via nested feel/delight paths already done
- **Prompt / schema / artifact:** out `master/master.wav`
- **Why weak:** blocked on ledger/seam/EDL archive races; optimizer apply failure = loud-fail; PMQ + delight floors at ship; input checks pin producers ambiguously under thrash
- **L/S:** L2 | S3
- **Status:** OPEN_RISK
- **fix-cluster:** `finalize-ledger-seam-pmq`
- **Evidence:** `stages/mastering.py:run_master_finalize` · `post_master_quality.py` · `stage_input_checks._check_master_finalize` · `tests/test_mastering.py` / `test_post_master_quality.py`

---

### STG-master_transcript_build-DEEP — Apple VTT from EDL + sidecars
- **Surface:** stage | ship | non-LLM
- **Modes:** all (`SHIP_AFTER_MASTER`)
- **Brain:** 0.1.0
- **Call graph:** `asset_transcripts.run_master_transcript_build` → `assemble_master_cues` → `rewrite_index` → `write_master_transcript_files` → `master/transcript.{json,vtt,txt}`
- **Local-ML / OpenAI:** none
- **Prompt / schema / artifact:** `master_transcript.schema.json` · `master/transcript.json` (+ VTT)
- **Why weak:** depends on VO/speech sidecars existing; missing sidecar → thin/wrong cues without STT re-run; publish will re-call this if VTT missing
- **L/S:** L2 | S2
- **Status:** OPEN_RISK
- **fix-cluster:** `master-transcript-sidecar-parity`
- **Evidence:** `asset_transcripts.py:run_master_transcript_build` · schema binding in `prompt_validation`

---

### STG-episode_meta_build-DEEP — title/description LLM
- **Surface:** stage | LLM | ship
- **Modes:** all
- **Brain:** 0.1.0
- **Call graph:** `run_episode_meta_build` → `run_llm_stage_simple` → `_persist_meta` → `publish/episode_meta.json`
- **Local-ML / OpenAI:** OpenAI (`llm_simple`, **flagship** in `model_registry`)
- **Prompt / schema / artifact:** `docs/prompts/publishing/episode-meta.system.txt`
- **Why weak:** hollow/generic meta still packages; no hard semantic QA beyond schema; depends on master transcript/context harvest quality
- **L/S:** L1 | S2
- **Status:** OPEN_RISK (quality) · structurally LIKELY_MITIGATED_ON_HEAD
- **fix-cluster:** `ship-meta-cover-quality`
- **Evidence:** `stages/podcast_publish.py:run_episode_meta_build`

---

### STG-episode_cover_prompt_craft-DEEP — cover prompt draft→finalize
- **Surface:** stage | LLM | ship
- **Modes:** all
- **Brain:** 0.1.0
- **Call graph:** `run_episode_cover_prompt_craft` → `run_prompt_envelope` draft (attempt 1) → finalize (attempt 2) → `_persist_cover_artifacts` / `_cover_craft_fallback` → `publish/cover_prompt.json` · max 2 chat attempts
- **Local-ML / OpenAI:** OpenAI chat (**flagship**)
- **Prompt / schema / artifact:** `docs/prompts/publishing/episode-cover-prompt.system.txt` · theme contract via `podcast_rss` cover helpers
- **Why weak:** rejected prompt (no silent truncate) → generate stage fail-opens to show artwork; fallback motifs can be generic
- **L/S:** L2 | S1
- **Status:** OPEN_RISK
- **fix-cluster:** `ship-meta-cover-quality`
- **Evidence:** `stages/podcast_publish.py:run_episode_cover_prompt_craft` · `docs/cross-cutting/podcast-cover-theme.md`

---

### STG-podcast_encode_mp3-DEEP — stereo MP3 + master copy
- **Surface:** stage | ship | local-audio
- **Modes:** all
- **Brain:** 0.1.0
- **Call graph:** `run_podcast_encode_mp3` → `require_publishable` → `encode_master_to_mp3` → `publish/` audio + master copy → `mark_done`
- **Local-ML / OpenAI:** none (ffmpeg encode)
- **Why weak:** blocked if PMQ not pass; otherwise mechanical — residual risk is upstream master quality, not encode itself
- **L/S:** L1 | S2
- **Status:** LIKELY_MITIGATED_ON_HEAD
- **fix-cluster:** `ship-package-local`
- **Evidence:** `stages/podcast_publish.py:run_podcast_encode_mp3` · `podcast_rss.encode`

---

### STG-episode_cover_generate-DEEP — OpenAI Images + vision pick
- **Surface:** stage | ship | OpenAI Images
- **Modes:** all
- **Brain:** 0.1.0
- **Call graph:** `run_episode_cover_generate` → `generate_cover_candidates` → vision pick (`episode-cover-vision-pick.system.txt` / local fallback) → `ensure_square_cover` → `publish/cover.jpg` + `cover_meta.json` · **except: fail-open `_copy_show_fallback`**
- **Local-ML / OpenAI:** OpenAI Images + vision (**flagship** pick) — not local-ML
- **Why weak:** hard-fail all candidates → show fallback still `mark_done` (publishable package with wrong art); cost/rebatch once
- **L/S:** L2 | S2
- **Status:** OPEN_RISK
- **fix-cluster:** `ship-meta-cover-quality`
- **Evidence:** `stages/podcast_publish.py:run_episode_cover_generate` · `podcast_rss.openai_cover` · `tests/test_podcast_rss.py`

---

### STG-podcast_publish-DEEP — local package_ready (no S3)
- **Surface:** stage | ship
- **Modes:** Manual G-Publish sync separate | Full-auto marks local ready | Partial
- **Brain:** 0.1.0
- **Call graph:** `run_podcast_publish` → `require_publishable` → ensure cover/chapters/VTT/mp3/master → write `publish/package_ready.json` + `publish_result.json` (`uploaded: false`) → `mark_done` · skip path `run_podcast_publish_skip`
- **Local-ML / OpenAI:** none
- **Why weak:** name implies publish but **no boto3/S3**; operator may think episode is live; can re-enter transcript build if VTT missing; advisories don’t block local package (`require_publishable` docstring)
- **L/S:** L1 | S1
- **Status:** LIKELY_MITIGATED_ON_HEAD (local) · OPEN_RISK for UX “uploaded” lie
- **fix-cluster:** `ship-package-local`
- **Evidence:** `stages/podcast_publish.py:run_podcast_publish` · port-manifest note “no S3” · `SHIP_AFTER_MASTER`

---

## Refine stages — in pipeline registry, **missing from `DELIVERY_ORDER`**

| Stage | In `DELIVERY_ORDER`? | In `pipeline` handlers? | HEAD behavior | port-manifest |
|---|---|---|---|---|
| `ranking_refine` | **No** | Yes → `run_ranking_refine` | `_noop_refine` identity mark | legacy / removed |
| `narrative_arc_refine` | **No** | Yes | `_noop_refine` | legacy / removed |
| `transitions_refine` | **No** | Yes | `_noop_refine` + `lint_gap_and_transitions` | legacy / removed |
| `sdp_intent_refine` | **No** | Yes | `_noop_refine` | legacy / removed |
| `edl_narrative_refine` | **No** | Yes | `_noop_refine` | legacy / removed |

Slim Pass-2 comment in `config.py`: “no-op `*_refine` removed.” Handlers retained so a forced/heal pin of those ids does not KeyError — they are **catalog-ghosts**, not delivery walk stages.

### STG-ranking_refine-DEEP / STG-narrative_arc_refine-DEEP / STG-transitions_refine-DEEP / STG-sdp_intent_refine-DEEP / STG-edl_narrative_refine-DEEP (shared)
- **Call graph:** `refinement_passes._noop_refine` → `decide_pass` → ledger / `heal_or_refuse_mark(force=True)`
- **Local-ML / OpenAI:** none
- **Why weak:** if agenda/heal still pins these ids, run marks “done” with **zero content mutate** (false sense of refine); only `transitions_refine` adds lint side-effect
- **L/S:** L2 | S1
- **Status:** OPEN_RISK (ghost stage) · intentional removal LIKELY_MITIGATED_ON_HEAD for default walk
- **fix-cluster:** `legacy-refine-noop-ghosts`
- **Evidence:** `v2/config.py:DELIVERY_ORDER` (absent) · `pipeline.py` handlers · `refinement_passes.py` · `docs/v2/port-manifest.csv` legacy rows · `refinement_identity.py` still lists them

---

## Ranked residual clusters (delivery/ship)

1. `junction-remaster-thrash` — L3/S4  
2. `musicgen-mmaudio-spend-thrash` — L3/S3  
3. `mix-edl-overlay-authority` — L3/S3  
4. `finalize-ledger-seam-pmq` — L2/S3  
5. `listen-delight-authority-timing` + `palette-cue-authority` — L2/S2  
6. `ship-meta-cover-quality` / `ship-package-local` — L1–L2 / S1–S2
