import type { PipelineSubTab } from "../../types";
import { useApp } from "../../context/AppContext";
import { subTabAttentionFlags } from "../../utils/attentionQueue";

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
  const { run, pipelineSubTab, setPipelineSubTab, apiGrants } = useApp();
  const flags = subTabAttentionFlags(run, apiGrants);

  return (
    <nav className="pipeline-v2-tool-row" aria-label="Pipeline tools">
      {TOOLS.map((t) => {
        const badge = flags[t.id] ?? 0;
        return (
          <button
            key={t.id}
            type="button"
            className={`btn ghost sm pipeline-tool-btn${pipelineSubTab === t.id ? " active" : ""}`}
            data-testid={`pipeline-tool-${t.id}`}
            title={badge > 0 ? `${t.label} — ${badge} need you` : t.label}
            onClick={() => setPipelineSubTab(t.id)}
          >
            {t.short}
            {badge > 0 ? <span className="tool-badge">{badge}</span> : null}
          </button>
        );
      })}
    </nav>
  );
}
