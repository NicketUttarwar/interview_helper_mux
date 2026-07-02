import { useState } from "react";
import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { useArtifactIssues } from "../../hooks/useArtifactIssues";
import { IssueResolutionCard } from "./IssueResolutionCard";
import { PropagationWizardPanel } from "./PropagationWizardPanel";

export function ArtifactClarificationPanel({ stage }: { stage: StageInfo }) {
  const { jobRunning, actionBusy, fixAllAndContinueStage } = useApp();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const {
    loading,
    busy,
    openItems,
    autoFixed,
    openBlocking,
    propagationPlan,
    preview,
    stepLabel,
    canFixAll,
    autoRepair,
    resolveIssue,
    executeAction,
    executePropagation,
    revalidate,
  } = useArtifactIssues(stage.id);

  const disabled = busy || jobRunning || actionBusy;

  if (loading && !openItems.length && !autoFixed.length) {
    return <p className="hint sm">Loading artifact issues…</p>;
  }

  return (
    <div className="stage-decision-panel" data-testid="stage-artifact-clarification">
      <p className="hint sm">
        {openBlocking
          ? `${openBlocking} blocking issue(s) remain. Use Fix all to apply recommended repairs when safe.`
          : "All blocking issues cleared — re-check validation or save staged files."}
      </p>
      {stepLabel ? (
        <p className="hint sm" data-testid="itr-lifecycle-phase">
          Remediation phase: <code>{String(stepLabel)}</code>
        </p>
      ) : null}

      {preview.length && openBlocking ? (
        <details className="itr-preview" open={showAdvanced}>
          <summary onClick={() => setShowAdvanced((v) => !v)}>
            Resolution preview ({preview.filter((p) => p.auto_resolvable).length} auto)
          </summary>
          <ul className="stage-step-prereq-list">
            {preview.map((p) => (
              <li key={String(p.issue_id)}>
                {p.message}
                {p.auto_resolvable ? " — auto" : " — manual"}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

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
        busy={disabled}
        onExecute={() => void executePropagation()}
      />

      {showAdvanced && openItems.length ? (
        <div className="itr-issue-list">
          {openItems.map((issue) => (
            <IssueResolutionCard
              key={issue.id}
              issue={issue}
              busy={disabled}
              onResolve={resolveIssue}
              onExecuteAction={executeAction}
            />
          ))}
        </div>
      ) : openItems.length ? (
        <p className="hint sm">
          {openItems.length} issue(s) need manual review. Open Advanced details for per-card fixes.
        </p>
      ) : (
        <p className="hint sm">No open blocking issues.</p>
      )}

      <div className="btn-row">
        <button
          type="button"
          className="btn primary sm"
          disabled={disabled || (!canFixAll && openBlocking > 0)}
          data-testid="itr-fix-all-continue"
          onClick={() => void fixAllAndContinueStage(stage.id)}
        >
          {String(stepLabel)}
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={disabled}
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? "Hide details" : "Advanced details"}
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={disabled}
          onClick={() => void autoRepair()}
        >
          Run auto-repair
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={disabled}
          onClick={() => void revalidate()}
        >
          Re-check validation
        </button>
      </div>
    </div>
  );
}
