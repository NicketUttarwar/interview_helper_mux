import type { StageInfo, StageStep } from "../../types";
import { useApp } from "../../context/AppContext";
import { guardBusy, type ShowToastFn } from "../../utils/guardBusy";
import {
  invokeStepFooterAction,
} from "../../utils/stageStepActions";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";

interface Props {
  step: StageStep;
  stage: StageInfo;
  isActive: boolean;
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
  } = useApp();

  const stageAction = useStageOperatorAction(run, stage.id, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  if (!isActive || !step.primary_button) return null;

  const busy = actionBusy || jobRunning;
  const disabled =
    busy ||
    step.status === "done" ||
    step.status === "waiting" ||
    step.status === "blocked" ||
    step.primary_button === "Running…";

  const onPrimary = () => {
    if (guardBusy(jobRunning, actionBusy, showToast as ShowToastFn)) return;
    void invokeStepFooterAction(step, stage, {
      executeJob: (body) => executeJob(body),
      runNextStage: () => runNextStage(),
      advanceFromCheckpoint: () => advanceFromCheckpoint(),
      skipOptional: (sid) => skipOptionalStage(sid),
      selectStage: (sid) => selectStage(sid),
      stageAction,
    });
  };

  const onSecondary = () => {
    if (!step.secondary_button) return;
    if (step.kind === "reuse") {
      void skipOptionalStage(stage.id);
      return;
    }
    if (step.secondary_button.toLowerCase().includes("redo")) {
      // Redo handled by StageOutputsPanel / done shell
      return;
    }
    if (step.secondary_button.toLowerCase().includes("discard")) {
      // WriteApprovalPanel owns discard
      return;
    }
  };

  return (
    <div className="stage-step-footer">
      <button
        type="button"
        className={`btn primary stage-step-primary${busy ? " running" : ""}`}
        data-testid="stage-step-primary"
        disabled={disabled}
        onClick={onPrimary}
      >
        {busy && step.kind === "run" ? (
          <span className="spinner-inline" aria-hidden />
        ) : null}
        {busy && step.kind !== "run" ? "Saving…" : step.primary_button}
      </button>
      {step.secondary_button ? (
        <button
          type="button"
          className="btn ghost sm stage-step-secondary"
          disabled={busy}
          onClick={onSecondary}
        >
          {step.secondary_button}
        </button>
      ) : null}
    </div>
  );
}
