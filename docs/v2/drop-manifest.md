# v2 drop manifest

Modules, surfaces, and behaviors **not ported** to the greenfield simplified app.

## Python modules (do not import in v2 default path)

| Module | Reason |
|--------|--------|
| `context_volley.py` | Cloud-only; no volley |
| `local_volley_framer.py` | Cloud-only |
| `local_llm_runner.py` | Cloud-only |
| `llm_stage_routing.py` (shard/collate/arbiter) | Replaced by `llm_simple.py` |
| `analysis_orchestrator.py` (investigation queue) | Linear pipeline |
| `attempt_budget.py` | Max 2 attempts in `llm_simple` |
| `holistic_fabrication.py` | Fail-closed |
| `micro_gap_fill.py` | Fail-closed |
| `custom_run_handoff.py` | No handoffs |
| `journey_orchestrator.py` (autopilot/ITR) | Linear run |
| `full_autopilot.py` | Dropped |
| `stages/disfluency.py` | G0.5 cut |
| Profile gate checks in `gates.py` | Cut |

`write_staging.py` remains for legacy compat but **bypassed** when `v2.auto_commit_artifacts: true`.

## Pipeline stages removed

| Stage | Reason |
|-------|--------|
| `disfluency_extract` | G0.5 cut |
| `disfluency_review` (gate) | G0.5 cut |
| `analysis_profile` (gate) | Profile gate cut |

## GUI surfaces removed

| Surface | Reason |
|---------|--------|
| Story Board tab | Simplified workbench |
| Debug tab | Simplified workbench |
| Volley tab | No volley |
| StageDecisionWizard | No autopilot |
| WriteApprovalPanel | Auto-commit |
| HandoffPanel | No handoffs |
| DisfluencyReviewPanel | G0.5 cut |
| AnalysisProfileGate | Profile cut |

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
- `docs/build-out/` → `docs/archive/pre-v2/build-out/`
- `requirements-local-mlx.txt`, `scripts/select_local_llm.py`, `scripts/download_local_llm.py`, `scripts/calibrate_local_llm.py`
- `ASSETS/executions/*`, `ASSETS/local_llm/`, all `*/venv` (recreated by `./scripts/bootstrap_venv.sh`)

## Operator action_ids quarantined

See `docs/cross-cutting/operator_action_catalog.json` — entries tagged `removed` in preservation matrix Pillar E plus:

- `gui.decision.*`
- `gui.autopilot.*`
- `gui.handoff.*`
- `gui.write_approval.*` (except batch logging if retained)
- `gui.disfluency_review.*`
- `gui.analysis_profile.*`
- `gui.g2.*`
