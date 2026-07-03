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
import { writeApprovalPrimaryLabel, writeApprovalSaveInProgressLabel } from "../../utils/writeApprovalLabels";
import { isWriteApprovalSaveInProgress } from "../../utils/jobStatus";

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
    redoFromStage,
    beginStageExecution,
    selectStage,
    approveWriteAndContinue,
    discardPendingWrites,
    completeTranscriptReview,
    completeDisfluencyReview,
    approveSfxPrompts,
    acknowledgeHandoff,
    revalidateArtifactIssues,
    fixAllAndContinueStage,
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

  const paths =
    step.kind === "write_approval" ? resolvePendingWritePaths(run, stage.id) : [];
  const saveInProgress =
    step.kind === "write_approval" &&
    isWriteApprovalSaveInProgress(run, { actionBusy, stageId: stage.id });
  const otherJobRunning = jobRunning && !saveInProgress;
  const busy = saveInProgress || otherJobRunning || (actionBusy && step.kind !== "write_approval");
  const isActionableCompleteStep =
    step.kind === "done" && Boolean(step.primary_button);
  const disabled =
    saveInProgress ||
    otherJobRunning ||
    (actionBusy && step.kind !== "write_approval") ||
    (step.status === "done" && !isActionableCompleteStep) ||
    step.status === "waiting" ||
    step.status === "blocked" ||
    primaryLabel === "Running…";

  const actionHandlers = {
    executeJob: (body: Parameters<typeof executeJob>[0]) => executeJob(body),
    runNextStage: () => runNextStage(),
    advanceFromCheckpoint: () => advanceFromCheckpoint(),
    approveWriteAndContinue: (sid: string) => approveWriteAndContinue(sid),
    revalidateArtifactIssues: (sid: string) => revalidateArtifactIssues(sid),
    fixAllAndContinueStage: (sid: string) => fixAllAndContinueStage(sid),
    discardPendingWrites: (sid: string) => discardPendingWrites(sid),
    completeTranscriptReview: (acceptUnreviewed?: boolean) =>
      completeTranscriptReview(acceptUnreviewed),
    completeDisfluencyReview: (acceptUnreviewed?: boolean) =>
      completeDisfluencyReview(acceptUnreviewed),
    approveSfxPrompts: () => approveSfxPrompts(),
    acknowledgeHandoff: () => acknowledgeHandoff(),
    skipOptional: (sid: string) => skipOptionalStage(sid),
    declineReuseAndRun: (sid: string) =>
      beginStageExecution({ kind: "decline_reuse_and_run", stageId: sid }),
    redoFromStage: () => redoFromStage(),
    selectStage: (sid: string) => selectStage(sid),
    stageAction,
  };

  const onPrimary = () => {
    if (saveInProgress) return;
    if (guardBusy(otherJobRunning, actionBusy && step.kind !== "write_approval", showToast as ShowToastFn)) {
      return;
    }
    void invokeStepFooterAction(step, stage, actionHandlers);
  };

  const onSecondary = () => {
    if (!step.secondary_button) return;
    if (saveInProgress) return;
    if (guardBusy(otherJobRunning, actionBusy && step.kind !== "write_approval", showToast as ShowToastFn)) {
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
        className={`btn primary stage-step-primary${saveInProgress || (busy && step.kind === "run") ? " running" : ""}`}
        data-testid={stepPrimaryTestId(step)}
        data-action-id={primaryActionId}
        disabled={disabled}
        aria-busy={saveInProgress || undefined}
        onClick={onPrimary}
      >
        {saveInProgress ? (
          <>
            <span className="spinner-inline" aria-hidden />
            {writeApprovalSaveInProgressLabel(paths.length)}
          </>
        ) : busy && step.kind === "run" ? (
          <>
            <span className="spinner-inline" aria-hidden />
            {primaryLabel}
          </>
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
          disabled={saveInProgress || otherJobRunning || (actionBusy && step.kind !== "write_approval")}
          onClick={onSecondary}
        >
          {step.secondary_button}
        </button>
      ) : null}
    </div>
  );
}
