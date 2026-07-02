# GUI flow hardening — operator feedback contract

Canonical reference for **how every operator click and background job must behave** in the React GUI. Implementation lives in `frontend/src/`; smoke scripts in [operator-stage-checklists.md](./operator-stage-checklists.md).

**Related:** [ux-operator-model.md](./ux-operator-model.md) · [gui-surface-map.md](./gui-surface-map.md) · [operator-flow-audit.md](./operator-flow-audit.md) (#83)

---

## Principles

1. **No silent no-ops** — blocked clicks show a toast (`guardBusy`) or disabled button + spinner.
2. **One continuation kernel** — checkpoint completion uses `advanceFromCheckpoint()` → `advancePipeline()` (not ad-hoc `runNextStage` after gates).
3. **Modal + inline coexist** — `OperatorActionModal` auto-opens on `needs_you`; inline panels in `StageDetail` remain after dismiss.
4. **Sidebar reflects work** — `actionBusy` marks substeps `running` (write approval, profile verify, handoff ack).
5. **Job terminals are loud** — poll completion always toasts + focuses next blocker.

---

## Shared utilities

| Utility | Path | Role |
|---------|------|------|
| `guardBusy` | `frontend/src/utils/guardBusy.ts` | Toast when `jobRunning` or `actionBusy` blocks a primary CTA |
| `advanceFromCheckpoint` | `AppContext.tsx` | Close modal, refresh, collapse done stage, start next or focus blocker |
| `completeAnalysisProfile` | `frontend/src/utils/analysisProfileCheckpoint.ts` | PUT → verify POST → refresh → advance (Story / Profile / gate) |
| `useAsyncAction` | `frontend/src/hooks/useAsyncAction.ts` | Panel buttons: start toast, spinner, success/error |
| `jobCompletionHint` | `frontend/src/utils/jobCompletionHints.ts` | Stage-specific “what’s next” after job `complete` |
| `setCheckpointBusy` | `AppContext.tsx` | Sets global `actionBusy` during checkpoint saves |

---

## Primary CTA surfaces (must use `guardBusy`)

| Surface | Component | Notes |
|---------|-----------|-------|
| Step header | `StepActionHeader` via `StageDetail` | `data-testid="step-action-primary"` |
| Global header | `LiveStatusBar` via `useOperatorCommand` | Hidden primary on Pipeline tab |
| Attention banner | `PendingActionBanner` | `data-testid="pending-action-primary"` |
| Guidance items | `GuidanceActionButton` | Stage guidance checklist buttons |
| Sidebar substeps | `activateSubstep` in `AppContext` | Guard before navigation |
| Modal footer | `OperatorActionModal` | Disabled when `actionBusy` |

---

## Job lifecycle feedback

| `gui_job.status` | Operator feedback |
|------------------|-------------------|
| `running` | `ActionOverlay` + activity log Live tab + optional batch progress in `StepActionHeader` |
| `complete` | Success toast (`jobCompletionHint` + `journey.next_action`) + sidebar focus |
| `gate` / `needs_operator` | Info toast + modal auto-open (Pipeline tab) |
| `awaiting_write_approval` | Info toast + modal + write substep |
| `error` | Error toast + error substep in sidebar |

---

## Checkpoint panels (must call `advanceFromCheckpoint` when unblocking pipeline)

| Panel | Stage / gate |
|-------|----------------|
| `TranscriptReviewPanel` | G0 `transcript_review` |
| `DisfluencyReviewPanel` | G0.5 `disfluency_review` |
| `AnalysisProfileGate` + Story/Profile | `analysis_profile` |
| `VoPickupPanel` | G1 `g1_vo_pickup` |
| `FlowSelectPanel` | G2 `g2_flow_select` |
| `SfxPromptReviewPanel` | `sfx_prompt_craft` |
| `SfxPostListenPanel` | MMAudio post-listen |
| `StageReuseOfferCard` | Stage reuse |
| `WriteApprovalPanel` | Write approval (via `approveWriteAndContinue`) |
| `HandoffPanel` | Handoff ack (via `acknowledgeHandoff`) |
| `PickupSpeakerPanel` | TBiy pickup speaker confirm |
| `PreviewPickupPanel` | G1.5 post-preview pickup |
| `ConversationStudioPanel` | TBiy gap-report editor (review-only — no advance) |

Review-only panels (spinners + toasts, no advance): `AcousticProfilePanel`, `InterviewSpinePanel`, `CoherenceRisksPanel`, `ValueFeaturesPanel`, `SonicContextPanel`, `PlacementAdjustmentsPanel`, `DisfluencyRestorePanel`, `ConversationStudioPanel`.

---

## Sub-tab gating

Locked Story / Timeline / Profile tabs (`PipelineToolRow`): click shows toast with `pipelineSubTabAvailability.reason` (not silent `disabled`).

---

## Non-pipeline surfaces

| Surface | Component | Feedback |
|---------|-----------|----------|
| Start | `StartTab` | `startRun` toasts “Creating execution…”; Refresh spinner; session recovery Retry spinner |
| Executions | `ExecutionsTab` | Toast when session locked; Refresh spinner |
| Export footer | `DeliverableCard` | `useAsyncAction` on preview-listen milestone |
| File editor | `ArtifactEditor` | Save spinner + start/success/error toasts |
| Timeline | `SmartActionsPanel` + `useTimelineEditor` | Batch confirm start toast; `patchSegments` progress + success |
| Debug — Volley | `VolleyMemoryPanel` | Refresh/rebuild/save spinners; error toasts |
| Debug — LLM calls | `LlmCallsPanel` | Save/expand spinners; error toasts (existing) |

All surfaces follow the same **no silent no-op** rule: disabled + spinner during async work, or an explanatory toast.

---

## Modal lifecycle

| Event | Behavior |
|-------|----------|
| Auto-open | `needs_you` on Pipeline tab; respects dismiss per blocker key |
| Operator dismiss | `closeActionModal` — sticky until same blocker changes |
| Checkpoint success | `closeActionModalAfterSuccess` — no sticky dismiss |
| Gate cleared | Modal auto-closes when stage `done` / profile verified |
| Write saving | Modal closes while job runs write approval |

---

## Testing

```bash
cd frontend && npm test
```

Key suites: `buttonSanity.test.ts`, `gateAdvance.test.ts`, `analysisProfileCheckpoint.test.ts`, `guardBusy.test.ts`, `jobCompletionHints.test.ts`, `stageSubsteps.test.ts`.

E2E: `CURSOR_EXECUTE/flow1-gui-e2e/run.sh` — prefer `step-action-primary` → modal → gate testids.

---

## Doc maintenance

When adding a new gate, panel, or primary CTA, update this file, [gui-surface-map.md](./gui-surface-map.md), [operator-stage-checklists.md](./operator-stage-checklists.md), and extend `buttonSanity` / `gateAdvance` tests as needed.
