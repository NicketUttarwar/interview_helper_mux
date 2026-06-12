import type { PipelineSubTab } from "../../types";
import { useApp } from "../../context/AppContext";

const TOOLS: { id: PipelineSubTab; label: string; short: string }[] = [
  { id: "stage", label: "Stage", short: "Stage" },
  { id: "story", label: "Story board", short: "Story" },
  { id: "timeline", label: "Timeline", short: "Timeline" },
  { id: "profile", label: "Profile JSON", short: "Profile" },
  { id: "files", label: "Files", short: "Files" },
  { id: "llm_calls", label: "Debug", short: "Debug" },
  { id: "volley_memory", label: "Volley", short: "Volley" },
];

export function PipelineToolRow() {
  const { pipelineSubTab, setPipelineSubTab } = useApp();

  return (
    <nav className="pipeline-v2-tool-row" aria-label="Pipeline tools">
      {TOOLS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`btn ghost sm pipeline-tool-btn${pipelineSubTab === t.id ? " active" : ""}`}
          data-testid={`pipeline-tool-${t.id}`}
          title={t.label}
          onClick={() => setPipelineSubTab(t.id)}
        >
          {t.short}
        </button>
      ))}
    </nav>
  );
}
