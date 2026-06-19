import type { OperatorAction } from "../types/operatorAction";
import { stepModeLabel } from "../utils/resolveOperatorAction";

interface Props {
  action: OperatorAction;
  stepNumber?: number | null;
  onPrimary: () => void;
  onSecondary?: () => void;
  busy?: boolean;
}

export function StepActionHeader({
  action,
  stepNumber,
  onPrimary,
  onSecondary,
  busy = false,
}: Props) {
  const showSpinner = action.mode === "running" || busy;
  const modeLabel = stepModeLabel(action.mode);

  return (
    <section
      className={`step-action-header step-mode-${action.mode}`}
      data-testid="step-action-header"
      aria-live="polite"
      aria-busy={action.mode === "running"}
    >
      <div className="step-action-header-main">
        <span className="step-action-mode" data-testid="step-action-mode">
          {showSpinner ? (
            <span className="spinner-inline" aria-hidden />
          ) : null}
          {modeLabel}
        </span>
        <div className="step-action-copy">
          {stepNumber != null ? (
            <p className="step-action-step-num hint sm">
              Pipeline step {stepNumber}
            </p>
          ) : null}
          <h2 className="step-action-headline" data-testid="step-action-headline">
            {action.headline}
          </h2>
          {action.subline ? (
            <p className="step-action-subline hint">{action.subline}</p>
          ) : null}
          {action.progress ? (
            <p className="step-action-progress hint sm">
              Step {action.progress.current} of {action.progress.total}
              {action.progress.label ? ` — ${action.progress.label}` : ""}
            </p>
          ) : null}
        </div>
      </div>
      <div className="step-action-buttons">
        {action.primaryLabel && action.primaryKind !== "none" ? (
          <button
            type="button"
            className={`btn primary step-action-primary${showSpinner ? " running" : ""}`}
            data-testid="step-action-primary"
            aria-label={busy ? "Saving…" : action.primaryLabel}
            disabled={action.primaryDisabled || busy}
            onClick={onPrimary}
          >
            {showSpinner ? (
              <span className="spinner-inline" aria-hidden />
            ) : null}
            {busy ? "Saving…" : action.primaryLabel}
          </button>
        ) : action.primaryLabel ? (
          <span className="step-action-status-only">{action.primaryLabel}</span>
        ) : null}
        {action.secondaryLabel && onSecondary ? (
          <button
            type="button"
            className="btn ghost sm step-action-secondary"
            data-testid="step-action-secondary"
            disabled={busy && action.secondaryKind !== "skip_optional"}
            onClick={onSecondary}
          >
            {action.secondaryLabel}
          </button>
        ) : null}
      </div>
    </section>
  );
}
