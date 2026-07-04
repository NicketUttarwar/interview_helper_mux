import type { LogEntry } from "../../types";

interface Props {
  alerts: LogEntry[];
  onDismiss: (entry: LogEntry) => void;
}

export function PinnedAlertStrip({ alerts, onDismiss }: Props) {
  if (!alerts.length) return null;

  return (
    <div className="activity-log-pinned" data-testid="activity-log-pinned-strip">
      <div className="activity-log-pinned-head">
        <span className="activity-log-pinned-title">Alerts</span>
        <span className="activity-log-pinned-count">{alerts.length}</span>
      </div>
      <div className="activity-log-pinned-body">
        {alerts.map((entry, i) => (
          <PinnedRow
            key={`${entry.ts}-${entry.level}-${i}`}
            entry={entry}
            onDismiss={() => onDismiss(entry)}
          />
        ))}
      </div>
    </div>
  );
}

function PinnedRow({ entry, onDismiss }: { entry: LogEntry; onDismiss: () => void }) {
  const kind = entry.level === "error" ? "error" : "warning";
  return (
    <div className={`log-entry level-${kind} log-entry-compact activity-log-pinned-row`}>
      <span className={`log-level-dot level-${kind}`} aria-hidden />
      <span className="log-msg">{entry.message}</span>
      <button
        type="button"
        className="activity-log-pinned-dismiss"
        onClick={onDismiss}
        aria-label="Dismiss alert"
        title="Dismiss"
        data-testid="activity-log-pinned-dismiss"
      >
        ×
      </button>
    </div>
  );
}
