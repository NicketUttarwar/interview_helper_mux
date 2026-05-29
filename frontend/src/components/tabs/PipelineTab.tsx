import type { PipelineSubTab } from "../../types";
import { useApp } from "../../context/AppContext";
import { Sidebar } from "../workspace/Sidebar";
import { StageDetail } from "../workspace/StageDetail";
import { NlePanel } from "../workspace/NlePanel";
import { ProfilePanel } from "../workspace/ProfilePanel";
import { ArtifactEditor } from "../workspace/ArtifactEditor";

const SUB_TABS: { id: PipelineSubTab; label: string }[] = [
  { id: "stage", label: "Stage" },
  { id: "timeline", label: "Timeline" },
  { id: "profile", label: "Profile" },
  { id: "files", label: "Files" },
];

export function PipelineTab() {
  const { runId, run, pipelineSubTab, setPipelineSubTab, setActiveTab, openActionModal, pendingActionCount } =
    useApp();

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
            {pipelineSubTab === "timeline" ? <NlePanel /> : null}
            {pipelineSubTab === "profile" ? <ProfilePanel /> : null}
            {pipelineSubTab === "files" ? <ArtifactEditor /> : null}
          </section>
        </div>
      </div>
    </main>
  );
}
