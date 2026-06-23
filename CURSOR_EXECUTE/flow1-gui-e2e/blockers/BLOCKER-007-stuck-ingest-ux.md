# BLOCKER-007 — Stuck after ingest (UX regression)

**Status: resolved** (checkpoint continuation contract — modal auto-open, `advanceFromCheckpoint`, write-approval save → ingest chain).

## Symptom

Operator completes ingest but cannot advance to transcribe:

- No **Needs you** badge on StepActionHeader
- Write approval modal did not auto-open
- Sidebar shows ingest done but transcribe still locked with no clear CTA

## Expected (post UX simplification)

1. `gui_job.status` → `awaiting_write_approval` (or stage `awaiting_write_approval`)
2. `journey.active_operator_action.mode` → `needs_you`
3. Modal auto-opens; **Save & continue** visible (`write-approval-save-continue`)
4. After save, focus moves to transcribe (reuse modal if `stage_reuse` blocking)

## Driver recovery order

1. `data-testid="step-action-primary"` — Review & continue
2. `data-testid="write-approval-save-continue"`
3. `data-testid="checkpoint-continue"` (handoff/reuse footer only)
4. Sidebar `substep-write_approval` or first `.pipeline-substep-row.status-todo`

## Evidence to capture

- Screenshot of StepActionHeader + sidebar focus row
- `GET /api/runs/{id}` → `job`, `journey.blocking`, `journey.active_operator_action`
- Activity log lines around ingest complete
- **Dump last step** output showing `write_approval.approve` → `pipeline.stage.ingest` / `ingest.hash`

## Likely causes

- `userDismissedActionRef` — operator closed modal; primary on StepActionHeader should reopen
- Stale job poll showing `running` after stage done
- Missing `pending_write_paths` in job snapshot (refresh run)
