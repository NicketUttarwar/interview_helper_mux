import { useEffect, useMemo, useRef } from "react";
import { useApp } from "../../context/AppContext";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";
import {
  checkpointContinueEnabled,
  checkpointContinueLabel,
  continueHintForStage,
  findPendingFocusStage,
  getHandoffPathsLocal,
  stageTitleForId,
} from "../../utils/checkpoint";
import { pendingWriteInfo, stageAwaitingWriteApproval } from "../../utils/writeApproval";
import { buildNumberedStages } from "../../utils/pipelineNavigation";
import { resolvePrecleanOffer } from "../../utils/preclean";
import { GateActions } from "../gates/GateActions";
import { HandoffPanel } from "../workspace/HandoffPanel";
import { StageReuseSection } from "../guidance/StageReuseSection";
import { WriteApprovalPanel } from "../guidance/WriteApprovalPanel";
import { PrecleanOfferCard } from "../gates/PrecleanOfferCard";
import type { OperatorAction } from "../../types/operatorAction";
type ActivePanel = "write" | "reuse" | "gate" | "handoff" | "preclean" | null;

function panelFromAction(
  action: OperatorAction | null,
  run: NonNullable<ReturnType<typeof useApp>["run"]>,
  selectedStage: NonNullable<ReturnType<typeof useApp>["selectedStage"]>,
): ActivePanel {
  if (action?.mode !== "needs_you") return null;

  const reason = action.blockingReason;
  if (
    reason === "write_approval" ||
    stageAwaitingWriteApproval(run, selectedStage.id)
  ) {
    return "write";
  }
  if (reason === "stage_reuse" || run.job?.needs_stage_reuse) {
    return "reuse";
  }

  const handoffPaths = getHandoffPathsLocal(selectedStage, run.log_tail);
  const handoffPending =
    selectedStage.status === "done" &&
    handoffPaths.length > 0 &&
    !run.handoff_ack?.[selectedStage.id];

  if (reason === "handoff_review" || handoffPending) {
    return "handoff";
  }

  const precleanOffer = resolvePrecleanOffer(selectedStage, run.meta);
  if (
    reason === "preclean" ||
    action?.substepId?.includes("preclean") ||
    precleanOffer
  ) {
    return "preclean";
  }

  if (
    selectedStage.status === "action_required" ||
    (run.job?.status === "gate" && run.job.stage === selectedStage.id) ||
    (reason &&
      reason !== "write_approval" &&
      reason !== "stage_reuse" &&
      reason !== "handoff_review")
  ) {
    return "gate";
  }

  return null;
}

export function OperatorActionModal() {
  const {
    run,
    selectedStage,
    selectedStageId,
    closeActionModal,
    closeActionModalAfterSuccess,
    onCheckpointContinue,
    selectStage,
    apiGrants,
    actionBusy,
    jobRunning,
  } = useApp();

  const modalRef = useRef<HTMLDivElement>(null);

  const action = useStageOperatorAction(run, selectedStage?.id ?? null, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  const actionStage = run?.stages.find((s) => s.status === "action_required");

  useEffect(() => {
    if (actionStage && selectedStage && actionStage.id !== selectedStage.id) {
      void selectStage(actionStage.id);
    }
  }, [actionStage, selectedStage, selectStage]);

  const activePanel: ActivePanel = useMemo(() => {
    if (!run || !selectedStage) return null;
    return panelFromAction(action, run, selectedStage);
  }, [run, selectedStage, action]);

  useEffect(() => {
    if (!run || !selectedStage) return;
    if (jobRunning && activePanel === "write") {
      closeActionModal();
    }
  }, [jobRunning, activePanel, run, selectedStage, closeActionModal]);

  useEffect(() => {
    if (!run || !selectedStage || activePanel !== "gate") return;
    if (actionBusy || jobRunning) return;
    const gateCleared =
      selectedStage.status === "done" ||
      (selectedStage.id === "analysis_profile" && run.profile_verified);
    if (gateCleared) {
      closeActionModalAfterSuccess();
    }
  }, [
    run,
    selectedStage,
    activePanel,
    actionBusy,
    jobRunning,
    run?.profile_verified,
    closeActionModalAfterSuccess,
  ]);

  useEffect(() => {
    const root = modalRef.current;
    if (!root) return;
    const focusable = root.querySelector<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])',
    );
    focusable?.focus();
  }, [activePanel, selectedStage?.id]);

  const title = action?.headline ?? "Operator action";
  const statusSubline =
    action?.subline && action.subline !== title && !title.includes(action.subline)
      ? action.subline
      : "";

  const hideGenericContinue =
    activePanel === "write" ||
    activePanel === "reuse" ||
    activePanel === "gate" ||
    activePanel === "handoff" ||
    activePanel === "preclean";

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

  const continueEnabled = checkpointContinueEnabled(run, selectedStage, apiGrants);
  const continueLabel = checkpointContinueLabel(run, selectedStage, apiGrants);
  const writePending = pendingWriteInfo(run);
  const showHandoff = activePanel === "handoff";
  const precleanOffer = selectedStage
    ? resolvePrecleanOffer(selectedStage, run.meta)
    : null;
  const stepNumber = run
    ? buildNumberedStages(run.stages).find((n) => n.stage.id === selectedStage.id)?.number
    : null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="operator-action-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeActionModal();
      }}
    >
      <div
        className="modal-card panel modal-lg operator-action-modal"
        ref={modalRef}
        data-testid="operator-action-modal"
      >
        <div className="modal-head">
          <div>
            {stepNumber != null ? (
              <p className="hint sm modal-step-badge">Pipeline step {stepNumber}</p>
            ) : null}
            <h3 id="operator-action-modal-title">{title}</h3>
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

        <div className="modal-body-scroll">
          {activePanel === "reuse" ? (
            <section id="modal-reuse">
              <StageReuseSection stage={selectedStage} />
            </section>
          ) : null}
          {activePanel === "write" ? (
            <section id="modal-write-approval">
              <WriteApprovalPanel stage={selectedStage} />
            </section>
          ) : null}
          {activePanel === "handoff" ? (
            <section id="modal-handoff">
              <HandoffPanel />
            </section>
          ) : null}
          {activePanel === "gate" ? (
            <section id="modal-gates">
              <GateActions stage={selectedStage} />
            </section>
          ) : null}
          {activePanel === "preclean" && precleanOffer ? (
            <section id="modal-preclean" className="attention-required">
              <PrecleanOfferCard stage={selectedStage} offer={precleanOffer} />
            </section>
          ) : null}
          {!activePanel && action?.mode === "needs_you" ? (
            <section id="modal-gates-fallback">
              <GateActions stage={selectedStage} />
            </section>
          ) : null}
          {!activePanel && action?.mode !== "needs_you" ? (
            <p className="empty-state">No checkpoint is active for this step.</p>
          ) : activePanel === "preclean" && !precleanOffer ? (
            <p className="empty-state">Audio cleaning is already in progress or complete.</p>
          ) : null}
        </div>

        {!hideGenericContinue ? (
          <div className="modal-actions modal-footer">
            <button
              type="button"
              className="btn ghost"
              data-testid="modal-dismiss-footer"
              onClick={closeActionModal}
            >
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
        ) : (
          <div className="modal-actions modal-footer">
            <button
              type="button"
              className="btn ghost"
              data-testid="modal-dismiss-footer"
              onClick={closeActionModal}
            >
              Dismiss
            </button>
          </div>
        )}
        {!continueEnabled && activePanel === "write" ? (
          <p className="hint modal-continue-hint">
            {writePending?.paths.length
              ? "Staged files are listed above — click Save & continue to write them to disk and advance."
              : "Loading staged files… if this persists, use Retry above."}
          </p>
        ) : null}
        {!continueEnabled && activePanel === "gate" ? (
          <p className="hint modal-continue-hint">
            {continueHintForStage(selectedStage.id, run)}
          </p>
        ) : null}
        {!continueEnabled && activePanel === "reuse" ? (
          <p className="hint modal-continue-hint">
            Choose reuse from a prior execution or run this step fresh.
          </p>
        ) : null}
        {!continueEnabled && showHandoff ? (
          <p className="hint modal-continue-hint">
            Skim AI outputs above, then acknowledge to continue.
          </p>
        ) : null}
        {activePanel === "preclean" ? (
          <p className="hint modal-continue-hint">
            Click <strong>Run audio cleaning</strong> above to start — progress appears in the activity log.
          </p>
        ) : null}
      </div>
    </div>
  );
}
