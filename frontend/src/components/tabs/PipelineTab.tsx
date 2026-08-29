import { useCallback, useRef } from "react";
import { PipelineCompletePanel } from "../pipeline/PipelineCompletePanel";
import { GPublishPanel } from "../gates/GPublishPanel";
import { isPartialAcceleratedRun } from "../../utils/partialAcceleratedGuard";
import { isPipelineComplete } from "../../utils/pipelineAutopilot";
import { useApp } from "../../context/AppContext";
import { PipelineStepList } from "../pipeline/PipelineStepList";
import { PhaseWorkbench } from "../workspace/PhaseWorkbench";
import { StageStepWorkbench } from "../workspace/StageStepWorkbench";
import { isV2Enabled } from "../../utils/v2Phases";
import { JourneyShell } from "../journey/JourneyShell";
import { PipelineVoStatusPanel } from "../pipeline/PipelineVoStatusPanel";
import { useOverscrollRetry } from "../../hooks/useOverscrollRetry";
import {
  clearPendingCheckpointScroll,
  getPendingCheckpointScroll,
  tryScrollToCheckpoint,
} from "../../utils/checkpointScrollRetry";

export function PipelineTab() {
  const {
    runId,
    run,
    setActiveTab,
    serverActiveRunId,
    openRun,
    openRunLoading,
    sessionLoadError,
    retryOpenRun,
    sessionReady,
    activityLogCollapsed,
    refreshRun,
    config,
    partialAutoGPublish,
  } = useApp();

  const partialPublishCheckpoint =
    Boolean(run) &&
    isPartialAcceleratedRun(run) &&
    run?.meta?.partial_auto_complete !== true &&
    Boolean(partialAutoGPublish?.pending && partialAutoGPublish.package_ready && !partialAutoGPublish.skipped);

  const scrollRef = useRef<HTMLDivElement>(null);
  const handleOverscrollRetry = useCallback(async () => {
    await refreshRun();
    const pending = getPendingCheckpointScroll();
    if (pending && tryScrollToCheckpoint(pending)) {
      clearPendingCheckpointScroll();
    }
  }, [refreshRun]);
  const { overscrollLoading } = useOverscrollRetry(scrollRef, handleOverscrollRetry, Boolean(runId));

  if (!runId || !run) {
    const resumeId = runId || serverActiveRunId;
    return (
      <main className="view tab-view pipeline-empty">
        <section className="panel panel-compact">
          <h2>No active run</h2>
          <p className="hint">Start from the Start tab or resume a previous execution.</p>
          {sessionLoadError ? (
            <p className="hint pipeline-load-error" role="alert">
              {sessionLoadError}
            </p>
          ) : null}
          <div className="flow-choice">
            {resumeId ? (
              <button
                type="button"
                className="btn primary"
                disabled={!sessionReady || openRunLoading}
                onClick={() => void (runId ? retryOpenRun() : openRun(resumeId))}
              >
                {openRunLoading
                  ? "Loading…"
                  : runId
                    ? "Retry load"
                    : "Resume server session"}
              </button>
            ) : null}
            <button type="button" className="btn primary" onClick={() => setActiveTab("start")}>
              Go to Start
            </button>
            <button type="button" className="btn ghost" onClick={() => setActiveTab("executions")}>
              Browse runs
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="view workspace-shell pipeline-tab pipeline-v2">
      <JourneyShell>
        <PipelineVoStatusPanel />
        <div className="workspace-scroll" ref={scrollRef}>
          {overscrollLoading ? (
            <div className="overscroll-retry-indicator" aria-busy="true">
              <span className="spinner-inline" aria-hidden /> Checking…
            </div>
          ) : null}
          <div
            className={`pipeline-v2-body${activityLogCollapsed ? " log-collapsed" : ""} pipeline-v2-body--no-side-log`}
          >
            <PipelineStepList />
            <div className="pipeline-v2-main">
              {isPipelineComplete(run) ? (
                <>
                  <PipelineCompletePanel />
                  {partialPublishCheckpoint ? <GPublishPanel /> : null}
                </>
              ) : isV2Enabled(config) ? (
                <PhaseWorkbench />
              ) : (
                <StageStepWorkbench />
              )}
            </div>
          </div>
        </div>
      </JourneyShell>
    </main>
  );
}
