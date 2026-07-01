import type { LogEntry } from "../../types";
import type { PinnedAlertsSelection } from "../../utils/logStreams";

interface Props {
  selection: PinnedAlertsSelection;
  expanded: boolean;
  onToggleExpanded: () => void;
  onDismiss?: () => void;
}

export function PinnedAlertStrip({
  selection,
  expanded,
  onToggleExpanded,
  onDismiss,
}: Props) {
  const {
    primaryError,
    displayedErrors,
    displayedWarnings,
    errorOverflow,
    warningOverflow,
  } = selection;

  const hasAlerts = selection.allPinned.length > 0;
  if (!hasAlerts) return null;

  const errorsToShow = expanded ? displayedErrors : primaryError ? [primaryError] : [];
  const warningsToShow = expanded ? displayedWarnings : [];
  const extraErrors = errorOverflow;
  const extraWarnings = warningOverflow;

  return (
    <div
      className={`activity-log-pinned${expanded ? " is-expanded" : " is-collapsed"}`}
      data-testid="activity-log-pinned-strip"
    >
      <div className="activity-log-pinned-head">
        <span className="activity-log-pinned-title">Alerts</span>
        <div className="activity-log-pinned-actions">
          {!expanded && extraErrors > 0 ? (
            <span className="activity-log-pinned-badge level-error">+{extraErrors} errors</span>
          ) : null}
          {!expanded && extraWarnings > 0 ? (
            <span className="activity-log-pinned-badge level-warning">+{extraWarnings} warnings</span>
          ) : null}
          {expanded && extraErrors > 0 ? (
            <span className="activity-log-pinned-badge level-error sm">+{extraErrors} more</span>
          ) : null}
          {expanded && extraWarnings > 0 ? (
            <span className="activity-log-pinned-badge level-warning sm">+{extraWarnings} more</span>
          ) : null}
          <button
            type="button"
            className="btn ghost sm activity-log-pinned-toggle"
            onClick={onToggleExpanded}
            aria-expanded={expanded}
          >
            {expanded ? "Collapse alerts" : "Show all alerts"}
          </button>
          {onDismiss ? (
            <button type="button" className="btn ghost sm" onClick={onDismiss}>
              Dismiss
            </button>
          ) : null}
        </div>
      </div>
      <div className="activity-log-pinned-body">
        {errorsToShow.map((e, i) => (
          <PinnedRow key={`err-${e.ts}-${i}`} entry={e} kind="error" />
        ))}
        {warningsToShow.map((e, i) => (
          <PinnedRow key={`warn-${e.ts}-${i}`} entry={e} kind="warning" />
        ))}
      </div>
    </div>
  );
}

function PinnedRow({ entry, kind }: { entry: LogEntry; kind: "error" | "warning" }) {
  return (
    <div className={`log-entry level-${kind} log-entry-compact activity-log-pinned-row`}>
      <span className="log-msg">{entry.message}</span>
    </div>
  );
}
