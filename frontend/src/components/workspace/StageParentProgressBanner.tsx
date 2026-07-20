import { useMemo, useState } from "react";
import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { StageReviewGateBanner } from "../gates/StageReviewGateBanner";
import { resolveStageWorkbenchProgress } from "../../utils/resolveStageWorkbenchProgress";
import {
  invokeStepFooterAction,
  invokeStepFooterSecondaryAction,
} from "../../utils/stageStepActions";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";
import { guardBusy } from "../../utils/guardBusy";

interface Props {
  stage: StageInfo;
  showDoneShell: boolean;
  onReviewDetail?: () => void;
  onActivateStep?: (stepId: string) => void;
}

function ProgressBusyButton({
  busy,
  label,
  onClick,
  testId,
  actionId,
  disabled,
}: {
  busy: boolean;
  label: string;
  onClick: () => void;
  testId?: string;
  actionId?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="btn primary stage-parent-progress-primary"
      data-testid={testId}
      data-action-id={actionId}
      disabled={busy || disabled}
      aria-busy={busy || undefined}
      onClick={onClick}
    >
      {busy ? (
        <>
          <span className="spinner-inline" aria-hidden />
          Working…
        </>
      ) : (
        label
      )}
    </button>
  );
}

export function StageParentProgressBanner({
  stage,
  showDoneShell,
  onReviewDetail,
  onActivateStep,
}: Props) {
  const {
    run,
    config,
    jobRunning,
    actionBusy,
    apiGrants,
    showToast,
    executeJob,
    runNextStage,
    advanceFromCheckpoint,
    skipOptionalStage,
    redoFromStage,
    selectStage,
    completeTranscriptReview,
    approveSfxPrompts,
    beginStageExecution,
  } = useApp();

  const [stepBusy, setStepBusy] = useState(false);

  const progress = useMemo(
    () => resolveStageWorkbenchProgress(run, stage, showDoneShell, config),
    [run, stage, showDoneShell, config],
  );

  const stageAction = useStageOperatorAction(run, stage.id, {
    selectedStageId: stage.id,
    jobRunning,
    apiGrants,
  });

  if (!progress) return null;

  if (progress.reviewGateSpec) {
    return (
      <div className="stage-parent-progress-banner" data-testid="stage-parent-progress-banner">
        <div className="stage-parent-progress-banner-inner">
          <p className="stage-parent-progress-kicker">Complete this stage</p>
          <StageReviewGateBanner
            spec={progress.reviewGateSpec}
            stage={stage}
            onReviewDetail={onReviewDetail}
          />
        </div>
      </div>
    );
  }

  const primaryStep = progress.primaryStep;
  if (!primaryStep || !progress.attentionLabel) return null;

  const busy = stepBusy || jobRunning || actionBusy;
  const primaryLabel = primaryStep.primary_button || progress.attentionLabel;

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
    if (guardBusy(jobRunning, actionBusy, showToast)) return;
    setStepBusy(true);
    void invokeStepFooterAction(primaryStep, stage, actionHandlers).finally(() =>
      setStepBusy(false),
    );
  };

  const onSecondary = () => {
    const secondary = progress.secondaryStep;
    if (!secondary?.secondary_button) return;
    if (guardBusy(jobRunning, actionBusy, showToast)) return;
    setStepBusy(true);
    void invokeStepFooterSecondaryAction(secondary, stage, actionHandlers).finally(() =>
      setStepBusy(false),
    );
  };

  const detailStepId =
    primaryStep.embed === "transcript_review"
      ? "review_transcript"
      : primaryStep.id;

  return (
    <div className="stage-parent-progress-banner" data-testid="stage-parent-progress-banner">
      <div className="stage-parent-progress-banner-inner panel-inset">
        <div className="stage-parent-progress-copy">
          <p className="stage-parent-progress-kicker">Complete this stage</p>
          <h3 className="stage-parent-progress-title">{stage.title}</h3>
          {progress.attentionMessage ? (
            <p className="hint sm stage-parent-progress-lead">{progress.attentionMessage}</p>
          ) : null}
        </div>
        <div className="stage-parent-progress-actions">
          <ProgressBusyButton
            busy={busy}
            label={primaryLabel}
            testId="stage-parent-progress-primary"
            onClick={onPrimary}
          />
          {progress.secondaryStep?.secondary_button ? (
            <button
              type="button"
              className="btn ghost sm"
              disabled={busy}
              onClick={onSecondary}
            >
              {progress.secondaryStep.secondary_button}
            </button>
          ) : null}
          {onActivateStep && detailStepId ? (
            <button
              type="button"
              className="btn ghost sm"
              disabled={busy}
              onClick={() => onActivateStep(detailStepId)}
            >
              Open review panel
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
