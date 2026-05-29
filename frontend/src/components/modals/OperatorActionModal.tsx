import { useEffect, useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { getHandoffPathsLocal, checkpointContinueEnabled } from "../../utils/checkpoint";
import { GateActions } from "../gates/GateActions";
import { HandoffPanel } from "../workspace/HandoffPanel";

export function OperatorActionModal() {
  const {
    run,
    selectedStage,
    actionSummary,
    closeActionModal,
    onCheckpointContinue,
    selectStage,
  } = useApp();

  const actionStage = run?.stages.find((s) => s.status === "action_required");

  useEffect(() => {
    if (actionStage && selectedStage && actionStage.id !== selectedStage.id) {
      void selectStage(actionStage.id);
    }
  }, [actionStage, selectedStage, selectStage]);

  const title = useMemo(() => {
    if (!run) return "Operator action";
    const actionStage = run.stages.find((s) => s.status === "action_required");
    if (actionStage) return actionStage.title;
    if (run.job?.status === "gate" || run.job?.status === "needs_operator") {
      return "Pipeline paused";
    }
    return "Review outputs";
  }, [run]);

  if (!run || !selectedStage) {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true">
        <div className="modal-card panel">
          <p className="empty-state">Select a stage in Pipeline to continue.</p>
          <div className="modal-actions">
            <button type="button" className="btn ghost" onClick={closeActionModal}>
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  const handoffPaths = getHandoffPathsLocal(selectedStage, run.log_tail);
  const showHandoff =
    selectedStage.status === "done" &&
    handoffPaths.length > 0 &&
    !run.handoff_ack?.[selectedStage.id];
  const continueEnabled = checkpointContinueEnabled(run, selectedStage);

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card panel modal-lg">
        <div className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="btn ghost sm" onClick={closeActionModal} aria-label="Close">
            Close
          </button>
        </div>
        {actionSummary ? <p className="hint modal-summary">{actionSummary}</p> : null}

        <div className="modal-body-scroll">
          {showHandoff ? <HandoffPanel /> : null}
          <GateActions stage={selectedStage} />
        </div>

        <div className="modal-actions modal-footer">
          <button type="button" className="btn ghost" onClick={closeActionModal}>
            Dismiss
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={!continueEnabled}
            onClick={() => void onCheckpointContinue()}
          >
            Continue to next step
          </button>
        </div>
      </div>
    </div>
  );
}
