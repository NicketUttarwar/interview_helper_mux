import type { PropagationPlan } from "../../hooks/useArtifactIssues.types";

interface Props {
  plan: PropagationPlan | null;
  busy: boolean;
  onExecute: () => void;
}

function stageLabel(plan: PropagationPlan, stageId: string): string {
  return plan.stage_labels?.[stageId] ?? stageId.replace(/_/g, " ");
}

function invalidateLabel(plan: PropagationPlan): string {
  const from = plan.invalidate_from;
  if (!from) return "upstream";
  return stageLabel(plan, from);
}

export function PropagationWizardPanel({ plan, busy, onExecute }: Props) {
  if (!plan?.has_blocking) {
    return null;
  }

  const stale = plan.stale_stages ?? [];
  const errors = plan.cross_errors ?? [];

  return (
    <div className="itr-propagation-wizard panel-inset" data-testid="itr-propagation-wizard">
      <h4 className="stage-outputs-title">Downstream propagation required</h4>
      <p className="hint sm">
        Saving upstream fixes may leave downstream stages stale. Review affected stages before
        continuing.
      </p>
      {plan.tbiy_affected && plan.change_hint ? (
        <p className="itr-propagation-tbiy-hint hint sm" data-testid="itr-propagation-tbiy-hint">
          <strong>TBIY:</strong> {plan.change_hint}
        </p>
      ) : null}
      {stale.length ? (
        <ul className="stage-step-prereq-list">
          {stale.map((sid) => (
            <li key={sid}>
              <span>{stageLabel(plan, sid)}</span>
              <code className="muted sm"> {sid}</code>
            </li>
          ))}
        </ul>
      ) : null}
      {errors.length ? (
        <details className="itr-propagation-errors">
          <summary>Cross-validation errors ({errors.length})</summary>
          <ul className="stage-step-prereq-list">
            {errors.slice(0, 6).map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="btn-row">
        <button
          type="button"
          className="btn primary sm"
          disabled={busy || !plan.invalidate_from}
          onClick={() => void onExecute()}
          data-testid="itr-propagation-execute"
        >
          Invalidate &amp; re-run from {invalidateLabel(plan)}
        </button>
      </div>
    </div>
  );
}
