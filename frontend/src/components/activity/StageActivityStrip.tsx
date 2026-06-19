import { useApp } from "../../context/AppContext";
import { filterByStage } from "../../utils/logStreams";
import { escapeHtml, formatTs } from "../../utils";

export function StageActivityStrip() {
  const {
    logEntries,
    selectedStageId,
    setActivityLogTab,
    setActivityLogCollapsed,
  } = useApp();

  if (!selectedStageId) return null;

  const entries = filterByStage(logEntries, selectedStageId).slice(-3);

  if (!entries.length) return null;

  return (
    <div className="stage-activity-strip panel-inset">
      <div className="stage-activity-strip-head">
        <h4 className="stage-outputs-title">Recent step activity</h4>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            setActivityLogTab("step");
            setActivityLogCollapsed(false);
          }}
        >
          View in activity panel
        </button>
      </div>
      <div className="stage-activity-strip-body">
        {entries.map((e, i) => (
          <div
            key={`${e.ts}-${i}`}
            className={`log-entry level-${e.level || "info"} log-entry-compact`}
          >
            <span className="log-ts">{formatTs(e.ts)}</span>
            <span className="log-msg">{escapeHtml(e.message)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
