# Artifact Issue Triage & Remediation (ITR)

Unified pipeline for classifying, auto-repairing, and operator-resolving artifact validation issues before write approval.

## North star

**Full autopilot (default):** After each LLM stage, `finalize_stage_outputs()` in `stage_finalize.py` runs triage + auto-resolve + risk-based force advance **in the worker** — operators never click Fix all. Unresolved choices surface in the **Stage Decision Wizard** (`operator_decisions` substep). See [full-autopilot-operator-model.md](../workflows/full-autopilot-operator-model.md).

**Legacy mode (`journey_ui.full_autopilot: false`):** **Fix all & continue** remains the primary operator action on segment stages. One click applies recommended repairs, clears the `needs_clarification` gate when safe, and chains to write approval when configured.

Manual per-card dropdowns appear only when confidence or safety gates fail (legacy) or in the decision wizard (full autopilot).

## Flow

1. **Post-persist** — `run_triage_pipeline()` after staged artifacts are written.
2. **Pre-cross-validate** — triage before hard halt when `clarification_before_halt` is true.
3. **Pre-write-approval** — `assert_write_approval_itr_ok()` blocks save when blocking issues remain or propagation is required. Pending staged files for the approving stage are overlaid onto committed cross-validation reads so first-time saves cannot fail with false `{path} missing` errors.
4. **Auto-resolve** — `POST …/issues/auto-resolve` runs `auto_resolve_stage()` in `artifact_auto_resolve.py`.
5. **Operator UI** — `artifact_clarification` step with **Fix all & continue** primary button; Advanced details for manual cards.

## Auto-resolve algorithm

1. Idempotent exit when `open_blocking === 0`.
2. Run deterministic repairs via `run_triage_pipeline` (logs `itr.triage.start` / `itr.triage.complete`).
3. For each open blocking item (cap: `auto_resolve_max_issues_per_pass`):
   - Pick `recommended_choice` when confidence ≥ `auto_resolve_min_confidence` and gap ≥ `auto_resolve_confidence_gap`.
   - Apply via `resolve_issue()`; log `itr.auto_resolve.apply`.
4. Enforce destructive rails (`min_segments_after_auto_resolve`, `max_segments_deleted_per_fix_all`).
5. Revalidate staged artifacts (`revalidate_for_itr_gate(..., artifact_source=staged)`).
6. Clear `needs_clarification` gate; clear `manifest_propagation` investigations on success.
7. Optionally chain `segment_classification` when boundary fix succeeds (`auto_resolve_chain_downstream`, `max_downstream_auto_continue` cap).

## AutoResolveResult outcomes

| Outcome | Meaning |
|---------|---------|
| `success` | All blocking issues cleared (may still be `awaiting_save` or `downstream_job` phase) |
| `partial` | Some fixes applied; validation or downstream still blocked |
| `manual_required` | One or more issues need operator choice |
| `cap_exhausted` | `max_auto_resolve_attempts_per_stage` reached |
| `destructive_budget_exceeded` | Would delete too many segments |
| `no_staged_artifact` | No staged file to repair |
| `busy` | Run lock held (409) |

Phases: `local_fix`, `downstream_job`, `awaiting_save`, `complete`, `failed`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/issues` | Items + `summary` (preview, `can_fix_all`, `bridge_eligible`, tier) |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/issues/auto-resolve` | Bulk auto-resolve (`AutoResolveResult` JSON) |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/issues/revalidate` | Gate re-check (preferred over deprecated continue-after-checkpoint ITR branch) |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/issues/auto-repair` | Deterministic repair only |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/issues/{id}/resolve` | Single-issue apply |
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/propagation-plan` | Read-only stale downstream plan |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/propagation/execute` | Confirmed invalidate + rerun |

`POST …/continue-after-checkpoint` with `kind=artifact_clarification` delegates to auto-resolve (legacy path).

## Downstream propagation

- **Read-only plan:** `plan_stale_downstream()` — no summary mutation on GET.
- **Mutate on execute:** `invalidate_stale_downstream()` when propagation job starts.
- Revalidation uses read-only plan via `revalidate_downstream_for_stage()`.

## Segment repair foundation

- `repair_boundaries()` dedupes duplicate `segment_id` when `segment_overlap_policy=drop_duplicate_then_llm_pick`.
- `apply_choice_to_boundaries()` honors `delete_segment` and type picks on `boundaries.json`.
- `resolve_issue()` routes boundaries vs manifest correctly.

## ITR stage registry

`ITR_STAGE_CAPABILITIES` in `artifact_auto_resolve.py` drives step labels and tiers (`full` / `scaffold` / `manual`). `stage_steps.py` reads registry copy for the clarification step.

## Key modules

| Module | Role |
|--------|------|
| `artifact_auto_resolve.py` | Bulk auto-resolve, outcome contract, stage registry |
| `artifact_issue_triage.py` | Orchestrator: collect, classify, repair, revalidate, gates |
| `artifact_root_cause.py` | Upstream routing, stale downstream plan vs invalidate |
| `issue_severity_rules.py` | Severity + repair strategy classification |
| `artifact_repairs.py` | Deterministic repair catalog + boundary operator choices |
| `artifact_clarification_llm.py` | Local LLM option generation (MLX fail-open) |
| `operator_clarifications_store.py` | Load/save clarifications file |

## GUI job statuses

| Status | Meaning |
|--------|---------|
| `needs_clarification` | Blocking ITR items — use Fix all & continue |
| `awaiting_write_approval` | Clean staged outputs — save allowed |
| `gate` | Unrecoverable LLM failure (not ITR) |

## Config

See `analysis.artifact_issue_triage` in [config-keys.md](./config-keys.md):

- `auto_resolve_min_confidence`, `auto_resolve_confidence_gap`
- `max_auto_resolve_attempts_per_stage`, `auto_resolve_max_issues_per_pass`
- `min_segments_after_auto_resolve`, `max_segments_deleted_per_fix_all`
- `auto_resolve_chain_downstream`, `max_downstream_auto_continue`
- `auto_advance_after_itr_clear`, `segment_overlap_policy`

Also `analysis.flow_hardening.clarification_before_halt`.
