import { useApp } from "../../context/AppContext";
import { filterByStage } from "../../utils/logStreams";

export function StageActivityStrip() {
  const {
    logEntries,
    selectedStageId,
    setActivityLogTab,
    setActivityLogCollapsed,
  } = useApp();

  if (!selectedStageId) return null;

  const stageEntries = filterByStage(logEntries, selectedStageId);
  const hasErrors = stageEntries.some((e) => e.level === "error");

  if (!stageEntries.length) return null;

  return (
    <div className={`stage-activity-strip panel-inset${hasErrors ? " has-errors" : ""}`}>
      <div className="stage-activity-strip-head">
        <h4 className="stage-outputs-title">
          {hasErrors ? (
            <>
              <span className="log-level-dot level-error" aria-hidden /> Step has errors — see Activity log
            </>
          ) : (
            "Step activity in global log panel"
          )}
        </h4>
        <button
          type="button"
          className="btn ghost sm"
          data-action-id="gui.activity.open_step"
          onClick={() => {
            setActivityLogTab("step");
            setActivityLogCollapsed(false);
          }}
        >
          View in activity panel
        </button>
      </div>
    </div>
  );
}
