import type { StageInfo } from "../../types";
import { useArtifactIssues } from "../../hooks/useArtifactIssues";
import { IssueResolutionCard } from "./IssueResolutionCard";
import { PropagationWizardPanel } from "./PropagationWizardPanel";

export function ArtifactClarificationPanel({ stage }: { stage: StageInfo }) {
  const {
    loading,
    busy,
    openItems,
    autoFixed,
    openBlocking,
    propagationPlan,
    autoRepair,
    resolveIssue,
    executeAction,
    executePropagation,
    revalidate,
  } = useArtifactIssues(stage.id);

  if (loading && !openItems.length && !autoFixed.length) {
    return <p className="hint sm">Loading artifact issues…</p>;
  }

  return (
    <div className="stage-decision-panel" data-testid="stage-artifact-clarification">
      <p className="hint sm">
        Minor issues are auto-fixed when possible. Resolve remaining{" "}
        <strong>{openBlocking}</strong> blocking issue(s) before saving staged files.
      </p>

      {autoFixed.length ? (
        <details className="itr-auto-fixed">
          <summary>Auto-fixed ({autoFixed.length})</summary>
          <ul className="stage-step-prereq-list">
            {autoFixed.map((it) => (
              <li key={it.id}>{it.message}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <PropagationWizardPanel
        plan={propagationPlan}
        busy={busy}
        onExecute={() => void executePropagation()}
      />

      {openItems.length ? (
        <div className="itr-issue-list">
          {openItems.map((issue) => (
            <IssueResolutionCard
              key={issue.id}
              issue={issue}
              busy={busy}
              onResolve={resolveIssue}
              onExecuteAction={executeAction}
            />
          ))}
        </div>
      ) : (
        <p className="hint sm">No open blocking issues.</p>
      )}

      <div className="btn-row">
        <button
          type="button"
          className="btn ghost sm"
          disabled={busy}
          onClick={() => void autoRepair()}
        >
          Run auto-repair
        </button>
        <button
          type="button"
          className="btn primary sm"
          disabled={busy}
          onClick={() => void revalidate()}
        >
          Re-check validation
        </button>
      </div>
    </div>
  );
}
