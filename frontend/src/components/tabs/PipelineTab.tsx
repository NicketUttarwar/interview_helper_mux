import type { PipelineSubTab } from "../../types";
import { useApp } from "../../context/AppContext";
import { Sidebar } from "../workspace/Sidebar";
import { StageDetail } from "../workspace/StageDetail";
import { NlePanel } from "../workspace/NlePanel";
import { ProfilePanel } from "../workspace/ProfilePanel";
import { ArtifactEditor } from "../workspace/ArtifactEditor";
import { LlmCallsPanel } from "../workspace/LlmCallsPanel";
import { StoryBoardPanel } from "../workspace/StoryBoardPanel";
import { JourneyShell } from "../journey/JourneyShell";

const SUB_TABS: { id: PipelineSubTab; label: string }[] = [
  { id: "stage", label: "Stage" },
  { id: "story", label: "Story" },
  { id: "timeline", label: "Timeline" },
  { id: "profile", label: "Profile (JSON)" },
  { id: "files", label: "Files" },
  { id: "llm_calls", label: "Engineering" },
];

export function PipelineTab() {
  const {
    runId,
    run,
    pipelineSubTab,
    setPipelineSubTab,
    setActiveTab,
    openActionModal,
    pendingActionCount,
    serverActiveRunId,
    openRun,
  } = useApp();

  if (!runId || !run) {
    return (
      <main className="view tab-view pipeline-empty">
        <section className="panel">
          <h2>No active execution</h2>
          <p className="lead">
            Start a new run from <strong>Start</strong> or resume one from{" "}
            <strong>Executions</strong>.
          </p>
          <div className="flow-choice">
            {serverActiveRunId ? (
              <button
                type="button"
                className="btn primary"
                onClick={() => void openRun(serverActiveRunId)}
              >
                Resume server session ({serverActiveRunId})
              </button>
            ) : null}
            <button type="button" className="btn primary" onClick={() => setActiveTab("start")}>
              Go to Start
            </button>
            <button type="button" className="btn ghost" onClick={() => setActiveTab("executions")}>
              Browse executions
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="view workspace-shell pipeline-tab">
      <div className="workspace-scroll">
        <JourneyShell>
        <div className="workspace-layout">
          <Sidebar />
          <section className="main-panel pipeline-main">
            <div className="pipeline-toolbar">
              <nav className="app-subtabs" aria-label="Pipeline sections">
                {SUB_TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`app-subtab${pipelineSubTab === t.id ? " active" : ""}`}
                    onClick={() => setPipelineSubTab(t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </nav>
              {pendingActionCount > 0 ? (
                <button type="button" className="btn primary sm" onClick={openActionModal}>
                  Action required ({pendingActionCount})
                </button>
              ) : null}
            </div>
            {pipelineSubTab === "stage" ? <StageDetail /> : null}
            {pipelineSubTab === "story" ? <StoryBoardPanel /> : null}
            {pipelineSubTab === "timeline" ? <NlePanel /> : null}
            {pipelineSubTab === "profile" ? <ProfilePanel /> : null}
            {pipelineSubTab === "files" ? <ArtifactEditor /> : null}
            {pipelineSubTab === "llm_calls" ? <LlmCallsPanel /> : null}
          </section>
        </div>
        </JourneyShell>
      </div>
    </main>
  );
}
