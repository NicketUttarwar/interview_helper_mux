import { useApp } from "../context/AppContext";
import { useGlobalOperatorAction } from "../hooks/useOperatorAction";
import { isJobActivelyRunning } from "../utils/jobStatus";

function formatPhaseLabel(phase: string | undefined): string | null {
  if (!phase) return null;
  return phase.replace(/_/g, " ");
}

export function ActionOverlay() {
  const { jobRunning, run, selectedStageId, apiGrants } = useApp();
  const action = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });
  if (!jobRunning) return null;

  const job = run?.job;
  const stageTitle = action.stageId
    ? run?.stages.find((s) => s.id === action.stageId)?.title
    : null;
  const detailMessage =
    job?.message?.trim() ||
    (action.mode === "running" ? action.subline : null) ||
    action.headline;
  const phaseLabel = formatPhaseLabel(job?.phase);
  const stepIndex = job?.step_index;
  const stepTotal = job?.step_total;
  const hasStepProgress =
    stepIndex != null && stepTotal != null && stepTotal > 1;
  const pct =
    hasStepProgress && stepTotal > 0
      ? Math.min(100, Math.round((stepIndex / stepTotal) * 100))
      : null;

  const fallbackMessage =
    action.mode === "running"
      ? action.headline
      : isJobActivelyRunning(job)
        ? job?.message || action.headline
        : job?.message || action.headline || "Working…";

  return (
    <div
      className="action-overlay action-overlay-nonblocking"
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="action-overlay"
    >
      <div className="action-overlay-card action-overlay-card-wide">
        <div className="action-overlay-spinner" aria-hidden />
        {stageTitle ? (
          <p className="action-overlay-stage">{stageTitle}</p>
        ) : null}
        {phaseLabel ? (
          <p className="action-overlay-phase hint sm">{phaseLabel}</p>
        ) : null}
        <p className="action-overlay-message">{detailMessage || fallbackMessage}</p>
        {hasStepProgress ? (
          <div className="action-overlay-progress-block">
            <div
              className="action-overlay-progress-bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={stepTotal}
              aria-valuenow={stepIndex}
              aria-label={`${stageTitle ?? "Stage"} progress`}
            >
              <span
                className="action-overlay-progress-fill"
                style={{ width: `${pct ?? 0}%` }}
              />
            </div>
            <p className="hint sm action-overlay-progress-text">
              {stepIndex} / {stepTotal}
              {pct != null ? ` (${pct}%)` : ""}
            </p>
          </div>
        ) : null}
        <p className="hint sm action-overlay-hint">
          You can keep using the app — check Activity (Live) for log lines.
        </p>
      </div>
    </div>
  );
}
