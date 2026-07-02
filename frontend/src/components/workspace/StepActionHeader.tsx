import type { OperatorAction } from "../../types/operatorAction";
import { stepModeLabel } from "../../utils/resolveOperatorAction";

interface Props {
  action: OperatorAction;
  stepNumber?: number | null;
  whatsNext?: string | null;
}

export function StepActionHeader({ action, stepNumber, whatsNext }: Props) {
  const showSpinner = action.mode === "running";
  const modeLabel = stepModeLabel(action.mode);
  const isError = action.mode === "error";

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
          ) : isError ? (
            <span className="log-level-dot level-error" aria-hidden />
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
              {action.progress.label ? `${action.progress.label}: ` : ""}
              {action.progress.current} / {action.progress.total}
            </p>
          ) : null}
          {whatsNext ? (
            <p className="whats-next-bar hint sm">
              What&apos;s next: {whatsNext}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
