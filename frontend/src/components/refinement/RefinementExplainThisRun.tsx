import { useMemo, useState } from "react";
import { useApp } from "../../context/AppContext";
import { useRefinementSummary } from "../../hooks/useRefinementSummary";

/** Explain-this-run export — agenda, plan, ledger paths as markdown/JSON download. */
export function RefinementExplainThisRun() {
  const { run, runId } = useApp();
  const summary = useRefinementSummary(runId, run);
  const [copied, setCopied] = useState(false);

  const markdown = useMemo(() => {
    if (!run) return "";
    const agenda = summary.agenda;
    const lines = [
      `# Refinement explain — ${run.run_id || runId || "run"}`,
      "",
      "## Agenda",
      `- Tape character: ${(agenda?.tape_character || []).join(", ") || "—"}`,
      `- Eligible: ${(agenda?.eligible_classes || []).join(", ") || "—"}`,
      `- Policy pack: ${agenda?.policy_pack_id || "—"}`,
      "",
      "## Gate plan",
      summary.plan
        ? "```json\n" + JSON.stringify(summary.plan, null, 2) + "\n```"
        : "_No refinement_plan.json yet_",
      "",
      "## Listener outcome",
      summary.listener_outcome_trajectory
        ? "```json\n" + JSON.stringify(summary.listener_outcome_trajectory, null, 2) + "\n```"
        : "_No trajectory yet_",
      "",
      "## Artifacts",
      "- `understanding/refinement_agenda.json`",
      "- `understanding/refinement_ledger.json`",
      "- `understanding/refinement_plan.json`",
      "- `understanding/refinement_champion/`",
      "- `understanding/refinement_cascade.json`",
    ];
    return lines.join("\n");
  }, [run, runId, summary]);

  if (!run?.refinement_agenda && !summary.plan) return null;

  const download = () => {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `refinement-explain-${runId || "run"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyJson = async () => {
    const payload = {
      agenda: summary.agenda,
      plan: summary.plan,
      trajectory: summary.listener_outcome_trajectory,
      champion: summary.champion,
      cascade: summary.cascade,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <section className="refinement-explain panel-inset" aria-label="Explain this run">
      <h4 className="refinement-subsection-title">Explain this run</h4>
      <p className="hint sm">Export agenda, gates, champion, and cascade for dogfooding.</p>
      <div className="refinement-explain-actions">
        <button type="button" className="btn sm" onClick={download}>
          Download markdown
        </button>
        <button type="button" className="btn sm ghost" onClick={() => void copyJson()}>
          {copied ? "Copied JSON" : "Copy JSON"}
        </button>
      </div>
    </section>
  );
}
