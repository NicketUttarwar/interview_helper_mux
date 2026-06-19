import { useApp } from "../../context/AppContext";
import { PipelineStepList } from "../pipeline/PipelineStepList";
import { PipelineToolRow } from "../pipeline/PipelineToolRow";
import { ActivityLogPanel } from "../activity/ActivityLogPanel";
import { StageDetail } from "../workspace/StageDetail";
import { NlePanel } from "../workspace/NlePanel";
import { ProfilePanel } from "../workspace/ProfilePanel";
import { ArtifactEditor } from "../workspace/ArtifactEditor";
import { LlmCallsPanel } from "../workspace/LlmCallsPanel";
import { VolleyMemoryPanel } from "../workspace/VolleyMemoryPanel";
import { StoryBoardPanel } from "../workspace/StoryBoardPanel";
import { JourneyShell } from "../journey/JourneyShell";

export function PipelineTab() {
  const {
    runId,
    run,
    pipelineSubTab,
    setActiveTab,
    serverActiveRunId,
    openRun,
    openRunLoading,
    sessionLoadError,
    retryOpenRun,
    sessionReady,
    activityLogCollapsed,
  } = useApp();

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
        <div className="workspace-scroll">
          <div
            className={`pipeline-v2-body${activityLogCollapsed ? " log-collapsed" : ""}`}
          >
            <PipelineStepList />
            <div className="pipeline-v2-main">
              <PipelineToolRow />
              {pipelineSubTab === "stage" ? <StageDetail /> : null}
              {pipelineSubTab === "story" ? <StoryBoardPanel /> : null}
              {pipelineSubTab === "timeline" ? <NlePanel /> : null}
              {pipelineSubTab === "profile" ? <ProfilePanel /> : null}
              {pipelineSubTab === "files" ? <ArtifactEditor /> : null}
              {pipelineSubTab === "llm_calls" ? <LlmCallsPanel /> : null}
              {pipelineSubTab === "volley_memory" ? <VolleyMemoryPanel /> : null}
            </div>
            <ActivityLogPanel />
          </div>
        </div>
      </JourneyShell>
    </main>
  );
}
