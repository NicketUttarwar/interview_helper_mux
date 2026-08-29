import type { StageInfo, StageStep } from "../../types";
import { useApp } from "../../context/AppContext";
import { guardBusy, type ShowToastFn } from "../../utils/guardBusy";
import { formatApiError } from "../../utils/safeApi";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";
import {
  invokeStepFooterAction,
  invokeStepFooterSecondaryAction,
} from "../../utils/stageStepActions";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";

interface Props {
  step: StageStep;
  stage: StageInfo;
  isActive: boolean;
}

function stepPrimaryTestId(step: StageStep): string {
  if (step.id === "review_transcript" || step.id === "complete_g0")
    return "complete-transcript-review";
  if (step.id === "prompt_review") return "approve-sfx-prompts";
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
    partialAutoGPublish,
    executeJob,
    runNextStage,
    advanceFromCheckpoint,
    skipOptionalStage,
    redoFromStage,
    beginStageExecution,
    selectStage,
    completeTranscriptReview,
    approveSfxPrompts,
  } = useApp();

  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);

  const stageAction = useStageOperatorAction(run, stage.id, {
    selectedStageId,
    jobRunning,
    apiGrants,
    gPublish: partialAutoGPublish,
  });

  const primaryLabel = step.primary_button;

  if (!isActive || !primaryLabel) return null;

  const busy = jobBlocksUi || actionBusy;
  const isActionableCompleteStep =
    step.kind === "done" && Boolean(step.primary_button);
  const disabled =
    jobBlocksUi ||
    actionBusy ||
    (step.status === "done" && !isActionableCompleteStep) ||
    step.status === "waiting" ||
    step.status === "blocked" ||
    primaryLabel === "Running…";

  const actionHandlers = {
    executeJob: (body: Parameters<typeof executeJob>[0]) => executeJob(body),
    runNextStage: () => runNextStage(),
    advanceFromCheckpoint: () => advanceFromCheckpoint(),
    completeTranscriptReview: (acceptUnreviewed?: boolean) =>
      completeTranscriptReview(acceptUnreviewed),
    approveSfxPrompts: () => approveSfxPrompts(),
    skipOptional: (sid: string) => skipOptionalStage(sid),
    declineReuseAndRun: (sid: string) =>
      beginStageExecution({ kind: "decline_reuse_and_run", stageId: sid }),
    redoFromStage: () => redoFromStage(),
    selectStage: (sid: string) => selectStage(sid),
    stageAction,
  };

  const onPrimary = () => {
    if (guardBusy(jobRunning, actionBusy, showToast as ShowToastFn, { run, gPublish: partialAutoGPublish })) {
      return;
    }
    void invokeStepFooterAction(step, stage, actionHandlers).catch((reason) => {
      showToast(formatApiError(reason, step.primary_button || "Action"), "error");
    });
  };

  const onSecondary = () => {
    if (!step.secondary_button) return;
    if (guardBusy(jobRunning, actionBusy, showToast as ShowToastFn, { run, gPublish: partialAutoGPublish })) {
      return;
    }
    void invokeStepFooterSecondaryAction(step, stage, actionHandlers).catch((reason) => {
      showToast(formatApiError(reason, step.secondary_button || "Action"), "error");
    });
  };

  return (
    <div className="stage-step-footer">
      <button
        type="button"
        className={`btn primary stage-step-primary${busy && step.kind === "run" ? " running" : ""}`}
        data-testid={stepPrimaryTestId(step)}
        disabled={disabled}
        onClick={onPrimary}
      >
        {busy && step.kind === "run" ? (
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
          disabled={jobBlocksUi || actionBusy}
          onClick={onSecondary}
        >
          {step.secondary_button}
        </button>
      ) : null}
    </div>
  );
}
