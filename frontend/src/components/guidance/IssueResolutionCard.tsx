import { useState } from "react";
import type { ArtifactIssue } from "../../hooks/useArtifactIssues.types";

interface Props {
  issue: ArtifactIssue;
  busy: boolean;
  onResolve: (issueId: string, choice: unknown) => Promise<void>;
  onExecuteAction: (issueId: string, action: string, upstreamStage?: string) => Promise<void>;
}

export function IssueResolutionCard({ issue, busy, onResolve, onExecuteAction }: Props) {
  const options = issue.options || [];
  const [choice, setChoice] = useState<string>(String(options[0]?.value ?? ""));

  const handleApply = () => {
    if (choice.startsWith("rerun_upstream:")) {
      const stage = choice.split(":")[1];
      void onExecuteAction(issue.id, "rerun_upstream", stage);
      return;
    }
    void onResolve(issue.id, choice);
  };

  return (
    <div className="itr-issue-card panel-inset" data-testid={`itr-issue-${issue.id}`}>
      <div className="itr-issue-head">
        <span className={`itr-severity itr-severity--${issue.severity}`}>{issue.severity}</span>
        {issue.segment_id ? (
          <span className="itr-segment-id">{issue.segment_id}</span>
        ) : null}
        {issue.suggested_upstream_stage ? (
          <span className="itr-upstream-badge" title="Suggested upstream fix">
            ↑ {issue.suggested_upstream_stage.replace(/_/g, " ")}
          </span>
        ) : null}
      </div>
      <p className="hint sm">{issue.message}</p>
      {options.length ? (
        <label className="itr-choice-label">
          Resolution
          <select
            value={choice}
            disabled={busy}
            onChange={(e) => setChoice(e.target.value)}
          >
            {options.map((opt) => (
              <option key={String(opt.value)} value={String(opt.value)}>
                {opt.label}
                {typeof opt.confidence === "number"
                  ? ` (${Math.round(opt.confidence * 100)}%)`
                  : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {options.length ? (
        <button
          type="button"
          className="btn sm primary"
          disabled={busy || !choice}
          onClick={handleApply}
        >
          Apply
        </button>
      ) : null}
      {issue.recovery_actions?.length ? (
        <div className="itr-recovery-actions btn-row">
          {issue.recovery_actions
            .filter((a) => a.type !== "dismiss")
            .map((action) => (
              <button
                key={action.type + (action.stage ?? "")}
                type="button"
                className={`btn sm ${action.type === "rerun_upstream" ? "ghost" : "secondary"}`}
                disabled={busy}
                onClick={() =>
                  void onExecuteAction(issue.id, action.type, action.stage)
                }
              >
                {action.label}
              </button>
            ))}
        </div>
      ) : null}
    </div>
  );
}
