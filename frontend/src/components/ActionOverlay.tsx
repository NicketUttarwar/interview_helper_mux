import { useEffect, useState } from "react";
import { useApp } from "../context/AppContext";
import { useGlobalOperatorAction } from "../hooks/useOperatorAction";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { resolveOperatorCover } from "../utils/partialAcceleratedGuard";
import { partialMustActOverlayCopy } from "../utils/partialOperatorGates";

function formatPhaseLabel(phase: string | undefined): string | null {
  if (!phase) return null;
  return phase.replace(/_/g, " ");
}

export type ActionOverlayPlacement = "app" | "workbench";

/**
 * Single cover: busy spinner (any mode) or accelerated guardrail (partial-auto).
 * Unmounts at operator pauses.
 *
 * placement="app" — covers operator-body (not top bar / logs dock); skips accelerated
 * on Pipeline so the workbench host can scope blur to the middle panel only.
 * placement="workbench" — accelerated cover only, for pipeline-v2-main.
 */
export function ActionOverlay({ placement = "app" }: { placement?: ActionOverlayPlacement }) {
  const { jobRunning, run, selectedStageId, apiGrants, setActiveTab, activeTab, partialAutoGPublish } =
    useApp();
  const [peeking, setPeeking] = useState(false);
  const runId = run?.run_id;

  useEffect(() => {
    setPeeking(false);
  }, [runId]);

  useEffect(() => {
    if (activeTab !== "logs") setPeeking(false);
  }, [activeTab]);

  const cover = resolveOperatorCover(run, partialAutoGPublish, {
    jobRunning,
    // Logs tab (and dock) stay interactive — treat as peeking so cover lifts
    peeking: peeking || activeTab === "logs",
  });
  const action = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
    gPublish: partialAutoGPublish,
  });

  if (cover === "none") return null;

  if (cover === "accelerated") {
    // Pipeline hosts workbench-scoped blur over the middle panel only
    if (placement === "app" && activeTab === "pipeline") return null;
    if (placement === "workbench") {
      // workbench host is only mounted on Pipeline; still guard
      if (activeTab !== "pipeline") return null;
    }

    return (
      <div
        className="accelerated-run-overlay"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="accelerated-run-overlay-title"
        aria-live="polite"
        data-testid="accelerated-run-overlay"
        data-placement={placement}
      >
        <div className="accelerated-run-overlay-card">
          <p id="accelerated-run-overlay-title" className="accelerated-run-overlay-title">
            Accelerated run in progress
          </p>
          <p className="accelerated-run-overlay-message hint">
            {partialMustActOverlayCopy()}
          </p>
          <button
            type="button"
            className="btn ghost sm"
            data-testid="accelerated-run-overlay-view-logs"
            onClick={() => {
              setPeeking(true);
              setActiveTab("logs");
            }}
          >
            View logs
          </button>
        </div>
      </div>
    );
  }

  if (placement === "workbench") return null;

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
      className="action-overlay action-overlay-blocking"
      role="alertdialog"
      aria-modal="true"
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
      </div>
    </div>
  );
}
