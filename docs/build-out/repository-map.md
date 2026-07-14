# Repository map

How **docs**, **code**, **config**, **tools**, and **operator media** fit together.

**Build-out:** [implementation-guide.md](./implementation-guide.md) · [full-application-flow.md](./full-application-flow.md) · [stage-registry.md](./stage-registry.md) · [ticket-specs.md](./ticket-specs.md) · tickets: [README.md](./README.md) · backlog: [steps-forward.md](./steps-forward.md).

---

## Top-level layout

| Path | Role | Build-out / docs |
|------|------|------------------|
| `AGENTS.md` | Agent read order, gates, constraints | BUILD-000 |
| `README.md` | Repo entry, links to setup and docs | BUILD-000 |
| `SETUP.md` | Bootstrap, secrets, first run | BUILD-000 |
| `ASSETS/` | Operator media (gitignored): `input/`, `executions/`, `.gui/` — [assets-and-executions.md](../cross-cutting/assets-and-executions.md) | [capture](../pipeline/capture/README.md) |
| `config/` | `app.defaults.json`, `secrets/secrets.env` | BUILD-011 · [config-keys](../cross-cutting/config-keys.md) |
| `docs/` | Authoritative specs and prompts | Waves 0–7 |
| `src/interview_mux/` | Python package | Waves 1–5, 7 |
| `frontend/` | React + TypeScript operator GUI (Vite → `web/static/`); **substep UX:** `utils/stageSubsteps.ts`, `utils/activateSubstep.ts`, `utils/phaseSubsteps.ts`, `hooks/useStageProgress.ts`, `components/pipeline/{SubstepRow,StepDoneBanner,StepRunningConnector,StepListContextHeader,GatePanelShell}.tsx`; G0: `TranscriptReviewPanel`, `TranscriptDockViewer`, `FuzzyReplacePopover`; `src/schemas/` Zod from `tools/codegen_zod_schemas.py` | BUILD-014 |
| `tools/` | CLI wrappers (`run_analysis`, `run_flow`, QA checks, value-analysis) | BUILD-028, 051–052 |
| `scripts/` | `bootstrap_venv.sh`, `build_gui.sh`, `run.sh` | BUILD-010, 014 |
| `tests/` | pytest (prompt validation, transcript review, shell) | BUILD-054–055 |
| `.cursor/rules/` | IDE policy (logging, Context7) | — |

**Not in v1:** SQLite / `mux_store`, boto3, preset ladder A–E (see `AGENTS.md`).

---

## Python package (`src/interview_mux/`)

| Module | Responsibility | Ticket |
|--------|----------------|--------|
| `cli.py` | Typer CLI: `analysis`, `flow`, `serve`, default pipeline | BUILD-028, 051 |
| `config.py` | Merge defaults + secrets; model IDs | BUILD-011 |
| `run_context.py` | Run workspace paths, `.stage_done`, `ctx.log()`, hash-aware run ids | BUILD-012 |
| `source_audio_hash.py` | Pipeline WAV SHA-256; hash in `exec_NNN_<hash12>_TIMESTAMP` ids | — |
| `stage_execution_reuse.py` | Per-stage reuse offers, copy-from-prior-run, `run_meta.stage_reuse` | — |
| `write_staging.py` | `.pending_writes/` staging; approve/discard before final persist | — |
| `stage_guidance.py` | `stages[].guidance` and journey phase copy for GUI; guidance items expose stable `id` and optional `substep_label` for sidebar substeps | — |
| `file_store.py` | Locked JSON read/write | BUILD-012 |
| `session_log.py` | `gui_log.jsonl` append/read | BUILD-016 |
| `application_session.py` | Unified `application_state.json`, server bootstrap, session API payload | Session overhaul |
| `session_lineage.py` | Immediate-previous run resolution, hash match | Session overhaul |
| `artifact_lifecycle.py` | `outputs_view`, staged vs committed artifact phases | Session overhaul |
| `ui_truth.py` | Run snapshot invariant validation (T1–T10) | Session overhaul |
| `gui_session.py` | Back-compat re-exports delegating to `application_session` | BUILD-014 |
| `gates.py` | G0/G1/G2 checks, profile gate, narrative QC enforcement | BUILD-017, 081 |
| `narrative_qc.py` | Flow 1 topic/chapter validation (`validate_flow1_narrative`) | BUILD-067 |
| `pipeline.py` | Stage orders, `run_analysis`, `run_delivery/2/3` | BUILD-028, 035–036, 043–044, 080 |
| `analysis_orchestrator.py` | Investigation queue drain after LLM stages | BUILD-018 |
| `analysis_memory.py` | `analysis_state.json`, profile, queue | BUILD-018 |
| `context_volley.py` | LLM message volleys per stage | BUILD-013 |
| `context_resolver.py` | Runtime volley Q&A index read/write (`context_index.json`) | volley memory |
| `context_index_gui.py` | GUI/API for volley entry CRUD | volley memory |
| `backfill_volley_index.py` | Backfill `volley_entries` from `stage_runs` | volley memory |
| `prompt_validation.py` | JSON schema validation; `ARTIFACT_WRITE_VALIDATORS`, `STAGE_ARTIFACT_DISK_PATHS` | BUILD-001 |
| `artifact_completeness.py` | Gap-fill context, merge, `artifact_status`, incomplete re-run | artifact generation |
| `artifact_writes.py` | `write_validated_artifact` — merge + validate before disk | artifact generation |
| `maudio_runner.py` | REST SFX (no SDK) | BUILD-034, 042 |
| `nle_state.py` | `segments/nle_edits.json` | BUILD-068 (ranking + EDL) |
| `acoustic_profile.py` | Shared SAP load, `mix_contract`, volley compact helpers | gap-closure GC-F1 |
| `audio_timeline.py` | WAV duration, crossfade concat, chunk-by-bytes | gap-closure GC-F1 |
| `operator_quality.py` | Preclean checkpoints, `qc_summaries` on `run_meta` | gap-closure GC-F1/F3 |
| `mix_completeness.py` | VO/SFX completeness gate after `mix`/`REMOVED_mix_flow2` | gap-closure orchestration |
| `arbiter_expectations.py` | Load per-stage arbiter rubrics; merge into routing payload | LLM guidance |
| `deterministic_lint.py` | Pre-arbiter generic + stage-specific lint | LLM guidance |
| `attempt_budget.py` | Per-stage primary/arbiter attempt budgets | LLM guidance |
| `sdp_cross_validate.py` | Sound-design plan cross-artifact checks | LLM guidance |
| `placement_qa.py` | Post-SFX placement hints; `apply_placement_adjustments` at mix | LLM guidance |
| `artifact_cross_validate.py` | Hard/soft cross-artifact gates after LLM stages | LLM guidance |
| `llm_preflight.py` | Upstream artifact preflight before LLM calls | LLM guidance |
| `llm_flow_hardening.py` | Spend gates, `complete_llm_stage_or_halt`, mix block | LLM guidance |
| `prompt_examples.py` | Shared example-pack injection for system prompts | LLM guidance |
| `local_volley_framer.py` | On-device volley framing before OpenAI (`prepare_volley_for_llm`) | LLM guidance |
| `local_capability_router.py` / `local_capability_manifest.py` | Quality-allowlist fail-fast ladder + Stage-1 manifest | LLM guidance |
| `episode_structure.py` | Deterministic sparse episode slot_plan + segment_order | Structure / SDP |
| `local_llm_config.py` / `local_llm_runner.py` | Local MLX framer config + chat runner | LLM guidance |
| `llm_call_record.py` | Per-call OpenAI audit under `understanding/llm_calls/` | BUILD-013 |
| `llm_calls_gui.py` | GUI helpers for LLM call index | BUILD-014 |
| `stage_enrichment.py` | Stage-specific enrichment inputs for volleys | BUILD-013 |
| `show_notes_qc.py` | Flow 3 show-description validation | BUILD-045 |
| `stages/llm_runner.py` | OpenAI calls (`task_kind`, tier meta) | BUILD-013, 073 |
| `stages/analysis_stage.py` | Shared LLM stage runner + arbiter | BUILD-013, 073 |
| `stages/model_registry.py` | Tier → API ID resolution | BUILD-073 |
| `stages/llm_arbiter.py` | Post-primary verdict | BUILD-073 |
| `stages/llm_subtasks.py` | Shard/collate decompose | BUILD-073, 084 |
| `stages/llm_stage_routing.py` | Unified primary→arbiter→decompose routing | BUILD-084 |
| `stages/llm_shard_plans.py` | `DECOMPOSE_ELIGIBLE` + deterministic shard plans | BUILD-084 |
| `stages/llm_specialists.py` | Optional pre/post specialist passes | BUILD-084 |
| `stages/llm_routing_debug.py` | Stage attempt summaries for GUI | BUILD-084 |

**LLM guidance (GUIDE wave):** [llm-guidance-program.md](../cross-cutting/llm-guidance-program.md) · [stage-quality-scorecard.md](../cross-cutting/stage-quality-scorecard.md) · [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §18–20

### Stages (`src/interview_mux/stages/`)

| Module | Stage id(s) | Ticket |
|--------|-------------|--------|
| `ingest.py` | `ingest` | BUILD-020 |
| `transcribe_aws.py` | `transcribe` | BUILD-021 |
| `disfluency.py` | `disfluency_extract`, `disfluency_review` (G0.5) | — |
| `transcript_review.py` | `transcript_review_build`, `transcript_review` | BUILD-018 |
| `understanding.py` | `source_acoustic_profile`, `speaker_roles`, `content_context` | BUILD-022, 023, 082 |
| `segmentation.py` | `boundary_detection`, `segment_classification` | BUILD-023–024 |
| `gaps.py` | `missing_framing`, `optimal_questions`, `vo_ingest` | BUILD-025–027 |
| `edl_narrative_qc.py` | Final Flow 1 EDL narrative semantics | EDL narrative QC |
| `analysis_extended.py` | `topic_coverage_audit`, `narrative_arc_plan` | BUILD-029–030 |
| `selection.py` | ranking, transitions, sfx brief | BUILD-031–033, 068 |
| `REMOVED_selection_flow2.py` | highlights, sfx brief | BUILD-040–041 |
| `sfx_mmaudio.py` | `mmaudio_sfx/2` | BUILD-034, 042 |
| `sound_design.py` | `mix`, `REMOVED_mix_flow2` | BUILD-065 |
| `assembly.py` | `edl`, `mux_flow1` → `mix` | BUILD-035, 065, 067, 068 |
| `REMOVED_assembly_flow2.py` | `mux_flow2` → `REMOVED_mix_flow2` | BUILD-043, 065 |
| `mastering.py` | `master_finalize`, `REMOVED_master_flow2` | BUILD-036, 050 |
| `audio_preclean.py` | DeepFilterNet preclean (optional) | BUILD-019 |
| `REMOVED_publishing_flow3.py` | `REMOVED_podcast_show_description`, `REMOVED_export_show_description` | BUILD-045–046 |
| `edl_narrative_audit.py` | `edl_narrative_audit` flagship Flow 1 audit | EDL narrative QC |
| `sound_design_stages.py` | `sound_design_palettes`, `sound_design_plan/2`, `sfx_prompt_craft` | BUILD-061–064 |
| `sound_design_vo_finalize.py` | `sound_design_vo_finalize` — VO bridge measured durations | gap-closure GC-A3 |

### Web GUI (`src/interview_mux/web/`)

| Module | Responsibility | Ticket |
|--------|----------------|--------|
| `server.py` | FastAPI `/api/*` | BUILD-014 |
| `runner.py` | Background execute → `gui_job.json` | BUILD-015 |
| `stages.py` | Stage metadata for UI | BUILD-014 |
| `static/` | Vite-built React SPA (`index.html`, `assets/*`) — source in `frontend/` | BUILD-014 |
| `gui_bundle.py` | Static bundle integrity (`needs_gui_build`) for `run.sh` / prerequisites | — |

### Value analysis (`src/interview_mux/value_analysis/`)

| Module | Responsibility |
|--------|----------------|
| `config.py` | `value_analysis.*` flag helpers |
| `extract.py` | `extract_and_write_value_features`, optional hook after `content_context` |
| `features_transcript.py` / `features_audio.py` | Metrics → `understanding/value_features.json` |
| `spike_score.py` | Spike scorecard aggregation |

**Default:** on in shipped config (`value_analysis.enabled: true`, auto-extract after `content_context`); still not a separate `pipeline.py` stage.

**GUI ↔ docs:** [gui-surface-map.md](../workflows/gui-surface-map.md) · [api-reference.md](../workflows/api-reference.md)

---

## Tools and scripts

| Entry | Invokes | Ticket |
|-------|---------|--------|
| `scripts/bootstrap_venv.sh` | venv + `pip install -r requirements.lock` + editable package | BUILD-010 |
| `scripts/build_gui.sh` | Vite build: `frontend/` → `web/static/` | BUILD-014 |
| `scripts/run.sh` | Web GUI (`python -m interview_mux serve`; builds static if missing) | BUILD-014 |
| `tools/check_prerequisites.sh` | ffmpeg, ffprobe, aws, import smoke, `pip-audit` on `requirements.lock` | BUILD-010 |
| `tools/run_analysis.py` | Shared analysis | BUILD-028 |
| `tools/run_delivery.py` | Flow 1, 2, or 3 after G2 | BUILD-051 |
| `tools/verify_master.py` | LUFS + true-peak QA on `master.wav` | BUILD-052, BUILD-070 |
| `tools/validate_narrative.py` | Flow 1 topic/chapter checks; `--include-edl` adds timeline + EDL narrative checks | BUILD-067 + EDL narrative QC |
| `tools/validate_edl.py` | EDL timeline/mechanical validation for `master/edl.json` | BUILD-067 |
| `tools/verify_edl.py` | EDL schema validation for `master/edl.json` | BUILD-067 |
| `tools/extract_value_features.py` | Opt-in value metrics artifact | value-analysis |
| `tools/run_value_spike.py` | Spike scorecard aggregation | value-analysis |
| `tools/export_llm_calls.py` | Export labeled LLM call records + stage-run audit appendix | LLM guidance |
| `tools/validate_show_description.py` | Flow 3 show-description QC | BUILD-045 |
| `tools/run_disfluency_extract.py` | Standalone disfluency extract CLI | — |
| `tools/codegen_zod_schemas.py` | JSON Schema → Zod for `frontend/src/schemas/` | BUILD-014 |
| `src/interview_mux/master_qc.py` | Measurement + threshold checks (shared by CLI and GUI) | BUILD-070 |
| `src/interview_mux/mastering_bus.py` | pyloudnorm assembly-bus LUFS before limiter | BUILD-071 |

---

## Documentation tree (by concern)

| Folder | Purpose |
|--------|---------|
| `docs/pipeline/` | Per-stage I/O, one README per stage |
| `docs/prompts/` | LLM system prompts + examples |
| `docs/cross-cutting/` | Artifacts, schemas, toolchain, quality roadmaps |
| `docs/workflows/` | Gates, GUI, smoke test, troubleshooting |
| `docs/roadmap/` | Future-proofing guardrails |
| `docs/pipeline/value-analysis/` | Optional R&D spikes (not default product path) |
| `docs/build-out/` | Full build-out suite: [implementation-guide](./implementation-guide.md), [stage-registry](./stage-registry.md), [ticket-specs](./ticket-specs.md), tickets, repo map, steps forward |

**Hub:** [INDEX.md](../INDEX.md) · **Pipeline overview:** [pipeline.md](../pipeline.md)

---

## Config and schemas

| Path | Purpose |
|------|---------|
| `config/app.defaults.json` | Paths, model routing, web port |
| `config/secrets/secrets.env` | API keys (gitignored) |
| `docs/cross-cutting/json-schemas/` | Validation contracts |
| `docs/prompts/**/*.system.txt` | Authoritative LLM copy |

---

## Doc ↔ code gaps

**Status (Command 9 + GUIDE wave + BUILD-SS):** No open operator-facing gaps in the table below. Closed-loop soundscape policy (`soundscape_policy_build`, cue slots, fitness remediation, post-mix verify) is shipped — [soundscape-policy.md](../cross-cutting/soundscape-policy.md). ASSETS picker/resume, full mix (`mix`), G2 flow3, pre-clean offers, smart LLM routing, Flow 3 analysis-only entry, and the LLM guidance program (GUIDE-001–080) are shipped in code.

| Topic | Verification |
|-------|----------------|
| ASSETS-first input | `GET /api/assets`, `POST /api/runs`, `PUT /api/session/active` — `web/server.py`; runs under `ASSETS/executions/exec_*` |
| Full podcast mix | `mix` / `REMOVED_mix_flow2` in `pipeline.py`; listen + `verify_master.py` — [definition-of-done-signoff.md](./definition-of-done-signoff.md) §3 |
| Pre-clean offers | `POST …/preclean-offer`; never auto — `web/server.py`, `stages/audio_preclean.py` |
| Stage parity | `pipeline.py` orders = `web/stages.py` `EXECUTABLE_ORDER` — signoff §5 |
| Flow 3 analysis-only entry | `REMOVED_run_flow3` → `require_g1_clear` + `require_analysis_artifacts_complete` (no Flow 1 ranking); `REMOVED_podcast_show_description` preflight when `REMOVED_selected_flow: flow3` checks `content_brief.json`, `speakers.json`, `manifest.json` — `pipeline.py`, `llm_preflight.py`, [stage-registry.md](./stage-registry.md) Flow 3 |
| LLM guidance program | P0–P4 scorecard + quality layers — [llm-guidance-program.md](../cross-cutting/llm-guidance-program.md), [stage-quality-scorecard.md](../cross-cutting/stage-quality-scorecard.md), `attempt_budget.py`, `local_volley_framer.py`, `placement_qa.py` |

When you introduce a new gap, add a row here and a command in [remaining-build-commands.md](./remaining-build-commands.md). Manual release checklist: [definition-of-done-signoff.md](./definition-of-done-signoff.md).
