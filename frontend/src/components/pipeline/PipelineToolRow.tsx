import type { PipelineSubTab } from "../../types";
import { useApp } from "../../context/AppContext";
import { useGlobalOperatorAction } from "../../hooks/useOperatorAction";
import { subTabAttentionFlags } from "../../utils/attentionQueue";
import { subTabSubstepFlags } from "../../utils/stageSubsteps";

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
  const {
    run,
    pipelineSubTab,
    setPipelineSubTab,
    apiGrants,
    jobRunning,
    selectedStageId,
  } = useApp();
  const flags = subTabAttentionFlags(run, apiGrants);
  const operatorAction = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });
  const substepFlags = run
    ? subTabSubstepFlags(run, { jobRunning, apiGrants })
    : {};

  return (
    <nav className="pipeline-v2-tool-row" aria-label="Pipeline tools">
      {TOOLS.map((t) => {
        const badge = flags[t.id] ?? 0;
        const subInfo = substepFlags[t.id];
        const subBadge = subInfo?.count ?? 0;
        const totalBadge = Math.max(badge, subBadge);
        const needsYouHint =
          t.id === "stage" && operatorAction.mode === "needs_you"
            ? operatorAction.headline
            : null;
        const tooltip =
          needsYouHint ||
          (subInfo && subInfo.labels.length > 0
            ? `${t.label} — ${subInfo.labels.join("; ")}`
            : badge > 0
              ? `${t.label} — ${badge} need you`
              : t.label);
        return (
          <button
            key={t.id}
            type="button"
            className={`btn ghost sm pipeline-tool-btn${pipelineSubTab === t.id ? " active" : ""}`}
            data-testid={`pipeline-tool-${t.id}`}
            title={tooltip}
            onClick={() => setPipelineSubTab(t.id)}
          >
            {t.short}
            {totalBadge > 0 ? <span className="tool-badge">{totalBadge}</span> : null}
          </button>
        );
      })}
    </nav>
  );
}
