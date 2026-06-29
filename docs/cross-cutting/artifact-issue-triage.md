# Artifact Issue Triage & Remediation (ITR)

Unified pipeline for classifying, auto-repairing, and operator-resolving artifact validation issues before write approval.

## Flow

1. **Post-persist** — `run_triage_pipeline()` in `llm_stage_routing.finalize_stage_attempt` after staged artifacts are written.
2. **Pre-cross-validate** — `pipeline.py` and `artifact_cross_validate.py` run triage before hard `SystemExit` when `clarification_before_halt` is true.
3. **Pre-write-approval** — `assert_write_approval_itr_ok()` blocks save when open blocking clarifications remain or downstream propagation is required.
4. **Operator UI** — middle-panel `artifact_clarification` step with recovery action buttons and propagation wizard.

## Smart recovery (upstream + downstream)

After deterministic repairs and downstream revalidation:

1. **Local repair first** — overlap trim, orphan ref drop, enum coercion, etc.
2. **Downstream revalidate** — cross-artifact checks after `segment_classification` or `boundary_detection` fixes.
3. **Propagation wizard** — when downstream stages are stale or cross-validate fails, the UI shows affected stages and **Invalidate & re-run from …** (no silent upstream reruns).
4. **Upstream rerun** — operator confirms; `invalidate_from` earliest stale stage, one upstream stage job, re-triage on return (capped by `max_upstream_reruns_per_run`).

### Recovery action types (clarification items)

| Action | API | Effect |
|--------|-----|--------|
| `apply_repair` | `POST …/issues/{id}/execute-action` | Run deterministic repair for the issue |
| `rerun_upstream` | same | Invalidate from upstream stage; start single stage job |
| `dismiss` | same | Mark non-blocking / dismiss |

Clarification items may include `suggested_upstream_stage` and `recovery_actions[]` (see `artifact_root_cause.py`).

### Propagation endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/propagation-plan` | Stale stages, cross errors, suggested `invalidate_from` |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/propagation/execute` | Operator-confirmed invalidate + rerun |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/issues/revalidate` | Returns `downstream_errors` + `propagation_plan` |

Root-cause routing maps lint/crossval signals to upstream stages (e.g. timeline overlap → `boundary_detection`, orphan segment ref → `segment_classification`).

## Severity matrix

| Severity | Auto action | Operator |
|----------|-------------|----------|
| `noise` | Enqueue non-blocking investigation | Hidden |
| `minor` | Deterministic repair (null arrays, enum coercion) | None unless repair fails |
| `important` | Local LLM generates 2–4 options | Required pick |
| `critical` | Deterministic repair once; then LLM options | Required pick or delete/merge |

## Artifacts

- **Clarifications store:** `understanding/operator_clarifications.json` (schema: `docs/cross-cutting/json-schemas/operator_clarifications.schema.json`)
- **Audit trail:** `_meta.repairs[]` on patched artifacts when `record_repairs_in_artifact_meta` is true

## Key modules

| Module | Role |
|--------|------|
| `artifact_issue_triage.py` | Orchestrator: collect, classify, repair, revalidate, gates |
| `artifact_root_cause.py` | Upstream routing, stale downstream plan, propagation helpers |
| `issue_severity_rules.py` | Severity + repair strategy classification |
| `artifact_repairs.py` | Deterministic repair catalog (P0–P2 stages) |
| `artifact_clarification_llm.py` | Local LLM option generation (MLX fail-open) |
| `operator_clarifications_store.py` | Load/save clarifications file |

## GUI job statuses

| Status | Meaning |
|--------|---------|
| `needs_clarification` | Blocking ITR items with operator options |
| `awaiting_write_approval` | Clean staged outputs — save allowed |
| `gate` | Unrecoverable LLM failure (not ITR) |

## Config

See `analysis.artifact_issue_triage` and `analysis.flow_hardening.clarification_before_halt` in [config-keys.md](./config-keys.md).
