import type { PipelineSubTab } from "../../types";
import { useApp } from "../../context/AppContext";
import { PipelineCommandCenter } from "../pipeline/PipelineCommandCenter";
import { PipelineStepList } from "../pipeline/PipelineStepList";
import { StageDetail } from "../workspace/StageDetail";
import { NlePanel } from "../workspace/NlePanel";
import { ProfilePanel } from "../workspace/ProfilePanel";
import { ArtifactEditor } from "../workspace/ArtifactEditor";
import { LlmCallsPanel } from "../workspace/LlmCallsPanel";
import { VolleyMemoryPanel } from "../workspace/VolleyMemoryPanel";
import { StoryBoardPanel } from "../workspace/StoryBoardPanel";
import { JourneyShell } from "../journey/JourneyShell";

const TOOL_TABS: { id: PipelineSubTab; label: string; tooltip: string }[] = [
  { id: "story", label: "Story board", tooltip: "Themes and investigations" },
  { id: "timeline", label: "Timeline", tooltip: "Segment cuts (NLE)" },
  { id: "profile", label: "Profile JSON", tooltip: "Analysis profile editor" },
  { id: "files", label: "Files", tooltip: "Artifact file editor" },
  { id: "llm_calls", label: "Debug", tooltip: "LLM call audit" },
  { id: "volley_memory", label: "Volley", tooltip: "Volley Q&A memory index" },
];

export function PipelineTab() {
  const {
    runId,
    run,
    pipelineSubTab,
    setPipelineSubTab,
    setActiveTab,
    serverActiveRunId,
    openRun,
  } = useApp();

  if (!runId || !run) {
    return (
      <main className="view tab-view pipeline-empty">
        <section className="panel panel-compact">
          <h2>No active run</h2>
          <p className="hint">Start from the Start tab or resume a previous execution.</p>
          <div className="flow-choice">
            {serverActiveRunId ? (
              <button
                type="button"
                className="btn primary"
                onClick={() => void openRun(serverActiveRunId)}
              >
                Resume session
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

  const showTools = pipelineSubTab !== "stage";

  return (
    <main className="view workspace-shell pipeline-tab pipeline-v2">
      <JourneyShell>
        <div className="workspace-scroll">
          <PipelineCommandCenter />

          <div className="pipeline-v2-body">
            <PipelineStepList />
            <div className="pipeline-v2-main">
              {pipelineSubTab === "stage" || !showTools ? <StageDetail /> : null}
              {pipelineSubTab === "story" ? <StoryBoardPanel /> : null}
              {pipelineSubTab === "timeline" ? <NlePanel /> : null}
              {pipelineSubTab === "profile" ? <ProfilePanel /> : null}
              {pipelineSubTab === "files" ? <ArtifactEditor /> : null}
              {pipelineSubTab === "llm_calls" ? <LlmCallsPanel /> : null}
              {pipelineSubTab === "volley_memory" ? <VolleyMemoryPanel /> : null}

              <details className="pipeline-tools-drawer panel">
                <summary>Tools &amp; editors</summary>
                <div className="pipeline-tools-tabs">
                  <button
                    type="button"
                    className={`btn ghost sm${pipelineSubTab === "stage" ? " active" : ""}`}
                    onClick={() => setPipelineSubTab("stage")}
                  >
                    Step detail
                  </button>
                  {TOOL_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={`btn ghost sm${pipelineSubTab === t.id ? " active" : ""}`}
                      title={t.tooltip}
                      onClick={() => setPipelineSubTab(t.id)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </details>
            </div>
          </div>
        </div>
      </JourneyShell>
    </main>
  );
}
