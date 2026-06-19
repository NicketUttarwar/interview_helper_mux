import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { filterByStage } from "../../utils/logStreams";
import { escapeHtml, formatTs } from "../../utils";
import { resolvePendingAction } from "../../utils/pendingAction";
import { pendingActionToSubstep } from "../../utils/stageSubsteps";
import { useStageProgress } from "../../hooks/useStageProgress";

export function StageActivityStrip() {
  const {
    logEntries,
    selectedStageId,
    run,
    apiGrants,
    setActivityLogTab,
    setActivityLogCollapsed,
    activateSubstep,
  } = useApp();
  const { activeSubstep } = useStageProgress(selectedStageId);

  const pending = useMemo(
    () => (run && selectedStageId ? resolvePendingAction(run, apiGrants) : null),
    [run, selectedStageId, apiGrants],
  );

  const pendingOnStage =
    pending && selectedStageId && pending.stageId === selectedStageId ? pending : null;

  if (!selectedStageId) return null;

  const entries = filterByStage(logEntries, selectedStageId).slice(-3);

  if (!entries.length && !pendingOnStage) return null;

  return (
    <div className="stage-activity-strip panel-inset">
      {activeSubstep && (activeSubstep.status === "todo" || activeSubstep.status === "running") ? (
        <p className="hint sm stage-activity-substep">
          {activeSubstep.status === "running" ? (
            <span className="spinner-inline" aria-hidden />
          ) : null}
          Current: <strong>{activeSubstep.label}</strong>
        </p>
      ) : null}

      {pendingOnStage ? (
        <div className="stage-activity-cta" role="alert">
          <p className="stage-activity-cta-text">
            <strong>Action required:</strong> {pendingOnStage.message}
          </p>
          <button
            type="button"
            className="btn primary sm"
            onClick={() => activateSubstep(pendingActionToSubstep(pendingOnStage))}
          >
            {pendingOnStage.primaryLabel}
          </button>
        </div>
      ) : null}

      {entries.length ? (
        <>
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
        </>
      ) : null}
    </div>
  );
}
