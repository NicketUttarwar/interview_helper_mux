import { useApp } from "../context/AppContext";
import { stageTitleForId } from "../utils/checkpoint";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { useStageProgress } from "../hooks/useStageProgress";

export function ActionOverlay() {
  const { jobRunning, actionBusy, run } = useApp();
  const { activeSubstepGlobal } = useStageProgress();
  if (!jobRunning && !actionBusy) return null;

  const job = run?.job;
  const stageId = job?.current_stage || job?.stage;
  const stageTitle = stageId
    ? stageTitleForId(run?.stages, stageId) || stageId.replace(/_/g, " ")
    : null;

  let message: string;
  if (actionBusy) {
    message = activeSubstepGlobal?.label || "Saving staged outputs and advancing…";
  } else if (activeSubstepGlobal?.status === "running") {
    message = activeSubstepGlobal.label;
  } else if (isJobActivelyRunning(job)) {
    message = stageTitle
      ? `Running ${stageTitle} — logs stream in Activity below.`
      : "Pipeline step running — logs stream in Activity below.";
  } else if (job?.message) {
    message = job.message;
  } else {
    message = "Working…";
  }

  return (
    <div
      className="action-overlay"
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="action-overlay"
    >
      <div className="action-overlay-card">
        <div className="action-overlay-spinner" aria-hidden />
        <p className="action-overlay-message">{message}</p>
        {jobRunning && stageTitle ? (
          <p className="hint sm action-overlay-detail">Step: {stageTitle}</p>
        ) : null}
      </div>
    </div>
  );
}
