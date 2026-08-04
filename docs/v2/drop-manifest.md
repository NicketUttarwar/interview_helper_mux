# v2 drop manifest

Modules, surfaces, and behaviors **not ported** to the greenfield simplified app.

For what the v2 pipeline actually runs, see [`src/interview_mux/v2/config.py`](../../src/interview_mux/v2/config.py) (**29 analysis + 28 delivery = 57 stages**) and [port-manifest.csv](./port-manifest.csv).

## Kept (explicitly *not* dropped)

Listed here because earlier revisions of this manifest wrongly marked them dropped.

| Module | Role |
|--------|------|
| `local_volley_framer.py` | Local MLX volley framer — LX-01 prep, **fail-open** |
| `local_llm_runner.py`, `local_llm_config.py`, `local_llm_selection.py` | Local MLX runtime in `ASSETS/local_llm/venv`, fail-open |
| `first_try.py` | First-try reliability mode |
| `llm_simple.py` | The only cloud LLM path; max **2** attempts per stage |
| `llm_specialists.py` | Config-gated specialist prompts |

## Python modules (deleted — do not import)

| Module | Reason |
|--------|--------|
| `context_volley.py` | Cloud volley context assembly; replaced by `stage_input_helpers.py` |
| `llm_stage_routing.py`, `llm_shard_plans.py`, `llm_subtasks.py`, `llm_arbiter.py` | Shard / collate / arbiter routing; replaced by `llm_simple.py` |
| `analysis_orchestrator.py` | Investigation queue; replaced by linear stage order |
| `attempt_budget.py` | Max 2 attempts lives in `llm_simple.py` |
| `holistic_fabrication.py` | Fail-closed |
| `micro_gap_fill.py` | Fail-closed |
| `custom_run_handoff.py` | No handoffs |
| `journey_orchestrator.py`, `autopilot.py`, `full_autopilot.py` | Linear run; no autopilot |
| `operator_decisions.py`, `decision_copy.py` | No Decision Wizard |
| `backfill_volley_index.py` | Cloud volley index |
| `artifact_issue_triage.py`, `lint_repair_bridge.py`, `lint_adaptation.py`, `adaptive_context.py` | Adaptation / repair loop |
| `content_brief_collate.py` | Collate step removed with sharding |
| `propagation_plan.py` | ITR propagation |
| `s2s_context.py` | Superseded by `local_runtime.py` S2S |
| `json_canonical.py` | Folded into `artifact_writes.py` |
| `mastering_polish_loop.py`, `mastering_prompt_promotion.py`, `mastering_research_router.py` | Mastering research/polish loop |
| `stages/disfluency.py` | G0.5 cut |
| `stages/transcribe_aws.py` | Local MLX STT only (`stages/transcribe_local.py`) |
| `stages/vo_synthesize.py` | Chatterbox VO via `chatterbox_runner.py` |
| `stages/sfx_elevenlabs.py` | Local MMAudio only |
| `stages/assembly_flow2.py`, `stages/selection_flow2.py`, `stages/publishing_flow3.py` | Flow 2 / Flow 3 removed |
| Profile gate checks in `gates.py` | Cut |

`write_staging.py` remains for legacy compat but **bypassed** when `v2.auto_commit_artifacts: true`.

## Pipeline stages removed

| Stage | Reason |
|-------|--------|
| `disfluency_extract` | G0.5 cut |
| `disfluency_review` (gate) | G0.5 cut |
| `analysis_profile` (gate) | Profile gate cut |
| G2 flow selection | Single flow |
| Flow 2 / Flow 3 delivery orders | Single flow to `master/master.wav` |
| `transcribe` via AWS Transcribe | Local MLX STT is the only backend |
| `optimal_questions` | Renamed `gap_framing_compose` (legacy alias only) |

## GUI surfaces removed

| Surface | Reason |
|---------|--------|
| Story Board tab | Simplified workbench |
| Debug tab | Simplified workbench |
| Volley tab | No LLM volley review UI |
| Profile / Files pipeline sub-tabs | Stage + Timeline only |
| StageDecisionWizard | No autopilot |
| WriteApprovalPanel | Auto-commit |
| HandoffPanel | No handoffs |
| DisfluencyReviewPanel | G0.5 cut |
| AnalysisProfileGate | Profile cut |
| Flow picker (G2) | Single flow |

## Config defaults (v2)

| Key | v2 value |
|-----|----------|
| `v2.enabled` | `true` |
| `v2.auto_commit_artifacts` | `true` |
| `local_llm.enabled` | `false` |
| `disfluency_extract.enabled` | `false` |
| `journey_ui.full_autopilot` | `false` |
| `journey_ui.require_write_approval_per_stage` | `false` |
| `journey_ui.require_handoff_between_stages` | `false` |
| `journey_ui.story_board` | `false` |
| `g1_5_require_prompt_approval` | `false` |

## Removed paths (v2 cleanup)

- `CURSOR_EXECUTE/` — legacy agent runner
- `docs/build-out/` — deleted (ticket specs, wave plans, repository map); `docs/archive/pre-v2/` keeps only the pre-v2 stage contracts
- `ASSETS/executions/*`, all `*/venv` (recreated by `./scripts/bootstrap_venv.sh`)

Kept tooling for the local MLX framer (fail-open LX-01): `scripts/select_local_llm.py`, `scripts/download_local_llm.py`, and `ASSETS/local_llm/` (venv recreated by bootstrap).

## Operator action_ids quarantined

See `docs/cross-cutting/operator_action_catalog.json` — entries tagged `removed` in preservation matrix Pillar E plus:

- `gui.decision.*`
- `gui.autopilot.*`
- `gui.handoff.*`
- `gui.write_approval.*` (except batch logging if retained)
- `gui.disfluency_review.*`
- `gui.analysis_profile.*`
- `gui.g2.*`
