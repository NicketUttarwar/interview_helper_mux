# UX operator model

Canonical operator GUI model after the Pipeline UX simplification wave.

## Mental model

1. **Left sidebar** (`PipelineStepList`) — where you are in the numbered pipeline; one highlighted row when action is required.
2. **StepActionHeader** — top of each step's main panel: mode badge, headline, one primary button.
3. **OperatorActionModal** — checkpoint work (write approval, reuse, gates, handoff); auto-opens on `needs_you`.
4. **LiveStatusBar** — global status on all tabs; on **Pipeline** tab primary lives in **StepActionHeader** (status-only bar); other tabs show resolver primary.
5. **Feedback contract** — every click and job terminal shows toast and/or spinner; see [gui-flow-hardening.md](./gui-flow-hardening.md).

## Step modes

| Mode | Badge | Primary button |
|------|-------|----------------|
| `running` | Running | Disabled "Running…" |
| `needs_you` | Needs you | Stage-specific label from resolver (e.g. Save & continue, Choose reuse, Review outputs) — opens modal |
| `done` | Complete | Continue to next step |
| `locked` | Waiting | Disabled + prerequisite |
| `idle` | Ready | Run {stage title} |

## Component ownership

| Concern | Owner |
|---------|--------|
| Unified action resolution | `resolveOperatorAction.ts` |
| Busy-click guard | `guardBusy.ts` |
| Checkpoint continuation | `advanceFromCheckpoint` / `advancePipeline` |
| Step top bar | `StepActionHeader.tsx` |
| Checkpoint forms | `OperatorActionModal` + panel components |
| Substep checklist | Sidebar `PipelineStepList` only |
| Activity logs | `ActivityLogPanel` (right column) |
| Async panel actions | `useAsyncAction` hook |

## Copy templates (Prepare)

| Stage | Mode | Headline |
|-------|------|----------|
| `ingest` | running | Running Ingest — normalizing audio |
| `ingest` | needs_you | Review ingest outputs before saving |
| `transcribe` | needs_you (reuse) | Choose reuse or run fresh |
| `transcript_review` | needs_you | Review speech-to-text clips |

See [operator-gates.md](./operator-gates.md) for gate copy.
