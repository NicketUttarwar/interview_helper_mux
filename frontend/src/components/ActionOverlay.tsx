import { useApp } from "../context/AppContext";
import { useGlobalOperatorAction } from "../hooks/useOperatorAction";
import { isJobActivelyRunning } from "../utils/jobStatus";

export function ActionOverlay() {
  const { jobRunning, actionBusy, run, selectedStageId, apiGrants } = useApp();
  const action = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });
  if (!jobRunning && !actionBusy) return null;

  const job = run?.job;
  const message = actionBusy
    ? action.headline || "Saving staged outputs and advancing…"
    : action.mode === "running"
      ? action.headline
      : isJobActivelyRunning(job)
        ? job?.message || action.headline
        : job?.message || action.headline || "Working…";

  const stageTitle = action.stageId
    ? run?.stages.find((s) => s.id === action.stageId)?.title
    : null;

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
