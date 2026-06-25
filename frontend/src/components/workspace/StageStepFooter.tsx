import { useMemo } from "react";
import type { StageInfo, StageStep } from "../../types";
import { useApp } from "../../context/AppContext";
import { guardBusy, type ShowToastFn } from "../../utils/guardBusy";
import {
  invokeStepFooterAction,
  invokeStepFooterSecondaryAction,
} from "../../utils/stageStepActions";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";
import { resolvePendingWritePaths } from "../../utils/writeApproval";
import { writeApprovalPrimaryLabel } from "../../utils/writeApprovalLabels";
import { isWriteApprovalSaving } from "../../utils/jobStatus";

interface Props {
  step: StageStep;
  stage: StageInfo;
  isActive: boolean;
}

function stepPrimaryTestId(step: StageStep): string {
  if (step.kind === "write_approval") return "write-approval-save-continue";
  if (step.id === "complete_g0") return "complete-transcript-review";
  if (step.id === "complete_g05") return "complete-disfluency-review";
  if (step.id === "prompt_review") return "approve-sfx-prompts";
  if (step.kind === "handoff") return "handoff-acknowledge";
  return "stage-step-primary";
}

export function StageStepFooter({ step, stage, isActive }: Props) {
  const {
    run,
    selectedStageId,
    jobRunning,
    actionBusy,
    apiGrants,
    showToast,
    executeJob,
    runNextStage,
    advanceFromCheckpoint,
    skipOptionalStage,
    selectStage,
    approveWriteAndContinue,
    discardPendingWrites,
    completeTranscriptReview,
    completeDisfluencyReview,
    approveSfxPrompts,
    acknowledgeHandoff,
  } = useApp();

  const stageAction = useStageOperatorAction(run, stage.id, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  const primaryLabel = useMemo(() => {
    if (step.kind === "write_approval") {
      const paths = resolvePendingWritePaths(run, stage.id);
      return writeApprovalPrimaryLabel(paths.length);
    }
    return step.primary_button;
  }, [step.kind, step.primary_button, run, stage.id]);

  if (!isActive || !primaryLabel) return null;

  const savingWriteApproval = step.kind === "write_approval" && isWriteApprovalSaving(run?.job);
  const busy = actionBusy || jobRunning || savingWriteApproval;
  const disabled =
    busy ||
    step.status === "done" ||
    step.status === "waiting" ||
    step.status === "blocked" ||
    primaryLabel === "Running…";

  const actionHandlers = {
    executeJob: (body: Parameters<typeof executeJob>[0]) => executeJob(body),
    runNextStage: () => runNextStage(),
    advanceFromCheckpoint: () => advanceFromCheckpoint(),
    approveWriteAndContinue: (sid: string) => approveWriteAndContinue(sid),
    discardPendingWrites: (sid: string) => discardPendingWrites(sid),
    completeTranscriptReview: (acceptUnreviewed?: boolean) =>
      completeTranscriptReview(acceptUnreviewed),
    completeDisfluencyReview: () => completeDisfluencyReview(),
    approveSfxPrompts: () => approveSfxPrompts(),
    acknowledgeHandoff: () => acknowledgeHandoff(),
    skipOptional: (sid: string) => skipOptionalStage(sid),
    selectStage: (sid: string) => selectStage(sid),
    stageAction,
  };

  const onPrimary = () => {
    if (guardBusy(jobRunning, actionBusy, showToast as ShowToastFn)) return;
    void invokeStepFooterAction(step, stage, actionHandlers);
  };

  const onSecondary = () => {
    if (!step.secondary_button) return;
    if (guardBusy(jobRunning, actionBusy, showToast as ShowToastFn)) return;
    if (step.secondary_button.toLowerCase().includes("redo")) {
      return;
    }
    void invokeStepFooterSecondaryAction(step, stage, actionHandlers);
  };

  const primaryActionId =
    step.kind === "write_approval"
      ? "gui.write_approval.save"
      : step.kind === "handoff"
        ? "gui.handoff.acknowledge"
        : undefined;

  return (
    <div className="stage-step-footer">
      <button
        type="button"
        className={`btn primary stage-step-primary${busy ? " running" : ""}`}
        data-testid={stepPrimaryTestId(step)}
        data-action-id={primaryActionId}
        disabled={disabled}
        onClick={onPrimary}
      >
        {busy && step.kind === "run" ? (
          <span className="spinner-inline" aria-hidden />
        ) : null}
        {busy && step.kind === "write_approval" ? (
          <>
            <span className="spinner-inline" aria-hidden /> Saving to disk…
          </>
        ) : busy && step.kind !== "run" ? (
          "Saving…"
        ) : (
          primaryLabel
        )}
      </button>
      {step.secondary_button ? (
        <button
          type="button"
          className="btn ghost sm stage-step-secondary"
          data-action-id={
            step.kind === "write_approval" ? "gui.write_approval.discard" : undefined
          }
          disabled={busy}
          onClick={onSecondary}
        >
          {step.secondary_button}
        </button>
      ) : null}
    </div>
  );
}
