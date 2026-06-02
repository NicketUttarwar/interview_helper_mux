import { useEffect, useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { getHandoffPathsLocal, checkpointContinueEnabled } from "../../utils/checkpoint";
import { GateActions } from "../gates/GateActions";
import { ApiConsentGatePanel } from "../gates/ApiConsentGatePanel";
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
  const needsApiConsent =
    run.job?.status === "needs_operator" &&
    (run.job.message?.includes("API consent") ||
      Boolean(run.job.missing_api_providers?.length));

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
          {needsApiConsent ? <ApiConsentGatePanel /> : null}
          {showHandoff ? <HandoffPanel /> : null}
          <GateActions stage={selectedStage} />
        </div>

        <div className="modal-actions modal-footer">
          <button type="button" className="btn ghost" data-testid="modal-close" onClick={closeActionModal}>
            Dismiss
          </button>
          <button
            type="button"
            className="btn primary"
            data-testid="checkpoint-continue"
            disabled={!continueEnabled}
            onClick={() => void onCheckpointContinue()}
            title={
              needsApiConsent
                ? "Allow required APIs above, then use the sidebar or journey button to run again"
                : undefined
            }
          >
            Continue to next step
          </button>
        </div>
        {!continueEnabled && selectedStage.status === "action_required" ? (
          <p className="hint modal-continue-hint">
            Complete the steps above (save transcript, record VO, verify profile, etc.)
            before continuing.
          </p>
        ) : null}
        {needsApiConsent && !continueEnabled ? (
          <p className="hint modal-continue-hint">
            After allowing APIs, close this dialog and click the primary pipeline button
            to retry.
          </p>
        ) : null}
      </div>
    </div>
  );
}
