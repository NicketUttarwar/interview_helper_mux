import { useEffect, useMemo } from "react";
import { useApp } from "../../context/AppContext";
import {
  continueHintForStage,
  findPendingFocusStage,
  getHandoffPathsLocal,
  checkpointContinueEnabled,
  checkpointContinueLabel,
  stageTitleForId,
} from "../../utils/checkpoint";
import { pendingWriteInfo, stageAwaitingWriteApproval } from "../../utils/writeApproval";
import { resolvePendingAction } from "../../utils/pendingAction";
import { GateActions } from "../gates/GateActions";
import { HandoffPanel } from "../workspace/HandoffPanel";
import { StageGuidancePanel } from "../guidance/StageGuidancePanel";
import { StageReuseSection } from "../guidance/StageReuseSection";
import { WriteApprovalPanel } from "../guidance/WriteApprovalPanel";

export function OperatorActionModal() {
  const {
    run,
    selectedStage,
    actionSummary,
    closeActionModal,
    onCheckpointContinue,
    selectStage,
    apiGrants,
    actionBusy,
  } = useApp();

  const pending = useMemo(() => resolvePendingAction(run, apiGrants), [run, apiGrants]);

  const actionStage = run?.stages.find((s) => s.status === "action_required");

  useEffect(() => {
    if (actionStage && selectedStage && actionStage.id !== selectedStage.id) {
      void selectStage(actionStage.id);
    }
  }, [actionStage, selectedStage, selectStage]);

  const title = useMemo(() => {
    if (!run) return "Operator action";
    if (pending) return pending.title;
    const actionStage = run.stages.find((s) => s.status === "action_required");
    if (actionStage) return actionStage.title;
    if (run.job?.status === "gate" || run.job?.status === "needs_operator") {
      return "Pipeline paused";
    }
    return "Review outputs";
  }, [run, pending]);

  if (!run) return null;

  if (!selectedStage) {
    const focusId = findPendingFocusStage(run, apiGrants);
    const focusTitle = stageTitleForId(run.stages, focusId);
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true">
        <div className="modal-card panel">
          <p className="empty-state">
            {focusTitle
              ? `Loading checkpoint: ${focusTitle}…`
              : "Open Pipeline and select a stage, or wait for the checkpoint to load."}
          </p>
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
  const continueEnabled = checkpointContinueEnabled(run, selectedStage, apiGrants);
  const continueLabel = checkpointContinueLabel(run, selectedStage, apiGrants);
  const writePending = pendingWriteInfo(run);
  const statusSubline =
    pending?.message ||
    run.journey?.next_action ||
    run.job?.message ||
    (selectedStage.status === "action_required" ? "Complete the items below to continue." : "");

  const sectionNav = [
    { id: "modal-write-approval", label: "Save review", show: pending?.kind === "write_approval" },
    { id: "modal-reuse", label: "Reuse", show: pending?.kind === "stage_reuse" },
    { id: "modal-gates", label: "Your action", show: selectedStage.status === "action_required" },
    { id: "modal-handoff", label: "AI review", show: showHandoff },
    { id: "modal-guidance", label: "Guidance", show: Boolean(selectedStage.guidance) },
  ].filter((s) => s.show);

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card panel modal-lg">
        <div className="modal-head">
          <div>
            <h3>{title}</h3>
            {statusSubline ? <p className="hint modal-status-subline">{statusSubline}</p> : null}
          </div>
          <div className="modal-head-actions">
            <button
              type="button"
              className="btn ghost sm"
              onClick={closeActionModal}
              aria-label="Continue inline"
            >
              Continue inline
            </button>
            <button type="button" className="btn ghost sm" onClick={closeActionModal} aria-label="Close">
              Close
            </button>
          </div>
        </div>
        {actionSummary ? <p className="hint modal-summary">{actionSummary}</p> : null}

        {sectionNav.length > 1 ? (
          <nav className="modal-section-nav" aria-label="Checkpoint sections">
            {sectionNav.map((s) => (
              <a key={s.id} className="modal-section-link" href={`#${s.id}`}>
                {s.label}
              </a>
            ))}
          </nav>
        ) : null}

        <div className="modal-body-scroll">
          {pending?.kind === "stage_reuse" || run.job?.needs_stage_reuse ? (
            <section id="modal-reuse">
              <StageReuseSection stage={selectedStage} />
            </section>
          ) : null}
          {pending?.kind === "write_approval" ||
          stageAwaitingWriteApproval(run, selectedStage.id) ? (
            <section id="modal-write-approval">
              <WriteApprovalPanel stage={selectedStage} />
            </section>
          ) : null}
          {selectedStage.guidance && pending?.kind !== "write_approval" ? (
            <section id="modal-guidance">
              <StageGuidancePanel stage={selectedStage} />
            </section>
          ) : null}
          {showHandoff ? (
            <section id="modal-handoff">
              <HandoffPanel />
            </section>
          ) : null}
          {selectedStage.status === "action_required" ||
          (run.job?.status === "gate" && run.job.stage === selectedStage.id) ? (
            <section id="modal-gates">
              <GateActions stage={selectedStage} />
            </section>
          ) : null}
        </div>

        <div className="modal-actions modal-footer">
          <button type="button" className="btn ghost" data-testid="modal-close" onClick={closeActionModal}>
            Dismiss
          </button>
          <button
            type="button"
            className="btn primary"
            data-testid="checkpoint-continue"
            disabled={!continueEnabled || actionBusy}
            onClick={() => void onCheckpointContinue()}
          >
            {actionBusy ? (
              <>
                <span className="spinner-inline" aria-hidden /> Working…
              </>
            ) : (
              continueLabel
            )}
          </button>
        </div>
        {!continueEnabled && pending?.kind === "write_approval" ? (
          <p className="hint modal-continue-hint">
            {writePending?.paths.length
              ? "Staged files are listed above — click Save & continue to write them to disk and advance."
              : "Loading staged files… if this persists, use Retry above."}
          </p>
        ) : null}
        {!continueEnabled && selectedStage.status === "action_required" ? (
          <p className="hint modal-continue-hint">
            {continueHintForStage(selectedStage.id, run)}
          </p>
        ) : null}
        {!continueEnabled && pending?.kind === "stage_reuse" ? (
          <p className="hint modal-continue-hint">
            Choose reuse from a prior execution or run this step fresh.
          </p>
        ) : null}
        {!continueEnabled && showHandoff ? (
          <p className="hint modal-continue-hint">
            Skim AI outputs above, then acknowledge to continue.
          </p>
        ) : null}
      </div>
    </div>
  );
}
