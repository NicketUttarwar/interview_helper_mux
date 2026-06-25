# UX operator model

Canonical operator GUI model — **inline step workbench** (no checkpoint modals).

## Mental model

1. **Left sidebar** (`PipelineStepList`) — numbered pipeline stages; click a stage to open its steps in the middle panel.
2. **Middle panel** (`StageStepWorkbench`) — numbered steps 1..N with instruction, review checklist, embedded editors, and **one primary button** per active step (`data-testid="stage-step-primary"`).
3. **StepActionHeader** — mode badge + headline + "What's next" line (no primary button on Pipeline tab).
4. **Activity log** — right dock; Live / This step / All.
5. **Modals** — destructive confirm (`ConfirmDialog`) only.

## Step modes (stage-level)

| Mode | Badge | Operator action |
|------|-------|-----------------|
| `running` | Running | Watch activity log; run step shows spinner |
| `needs_you` | Needs you | Expand active numbered step; use step footer CTA |
| `done` | Complete | Review outputs; Continue to next stage |
| `locked` | Waiting | Go to blocking stage link |
| `idle` | Ready | Run step footer **Run {title}** |

## Component ownership

| Concern | Owner |
|---------|--------|
| Step list (server) | `build_stage_steps()` in `stage_steps.py` |
| Workbench UI | `StageStepWorkbench`, `StageStepRow`, `StageStepBody`, `StageStepFooter` |
| Busy-click guard | `guardBusy.ts` |
| Checkpoint continuation | `advanceFromCheckpoint()` |
| Session focus | `selected_stage_id` + `active_step_id` in `active_execution.json` |

See [gui-flow-hardening.md](./gui-flow-hardening.md) and [operator-stage-checklists.md](./operator-stage-checklists.md).
