import { useCallback } from "react";
import { useApp } from "../context/AppContext";
import { useLiveStatus } from "../hooks/useLiveStatus";
import { useGlobalOperatorAction } from "../hooks/useOperatorAction";
import { invokeOperatorActionPrimary, executeBodyForStage } from "../utils/operatorActionHandlers";
import {
  WORKFLOW_STEPS,
  currentWorkflowStep,
  stageIdForStep,
  stepNeedsCheckpoint,
  workflowStepIndex,
  workflowStepStatus,
  workflowStepAttentionCount,
  type WorkflowStepId,
} from "../utils/workflowSteps";
import { substepIdToStepId } from "../utils/resolveActiveStep";
import { SessionBanner } from "./SessionBanner";
import { PreviewListenPromo } from "./guidance/PreviewListenPromo";

export function LiveStatusBar() {
  const {
    run,
    jobRunning,
    selectedStageId,
    logEntries,
    apiGrants,
    executeJob,
    runNextStage,
    openActionModal,
    acknowledgeHandoff,
    approveWriteAndContinue,
    approveBatchWrites,
    selectStage,
    setActiveSubstepId,
    setActiveTab,
    setPipelineSubTab,
    showToast,
    sessionReady,
    pendingActionCount,
    setMenuOpen,
    menuOpen,
    clearSession,
    alertsMuted,
    setAlertsMuted,
    setLogFilterPreset,
    jobCompleteAt,
    activeTab,
    actionBusy,
  } = useApp();

  const statusOnlyOnPipeline = activeTab === "pipeline" && Boolean(run);

  const scrollToLogs = useCallback(
    (opts?: { errors?: boolean }) => {
      const errorCount = logEntries.filter((e) => e.level === "error").length;
      const toErrors = opts?.errors ?? errorCount > 0;
      setLogFilterPreset({
        stream: toErrors ? "all" : "live",
        level: toErrors ? "error" : undefined,
        scrollToError: toErrors,
      });
      setActiveTab("logs");
    },
    [logEntries, setLogFilterPreset, setActiveTab],
  );

  const scrollPreview = useCallback(() => {
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    requestAnimationFrame(() => {
      document.getElementById("preview-listen-promo")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    });
  }, [setActiveTab, setPipelineSubTab]);

  const live = useLiveStatus(run, {
    jobRunning,
    actionBusy,
    selectedStageId,
    logEntries,
    apiGrants,
    activeTab,
    onExecute: (body) => void executeJob(body),
    onRunNext: () => void runNextStage(),
    onOpenCheckpoint: (stageId, substepId) => {
      if (stageId) {
        const stepId = substepIdToStepId(substepId);
        void selectStage(stageId, { stepId });
      }
      if (substepId) setActiveSubstepId(substepId);
      openActionModal();
    },
    onAcknowledgeHandoff: () => void acknowledgeHandoff(),
    onApproveWrite: (stageId) => void approveWriteAndContinue(stageId),
    onGoLogs: () => scrollToLogs(),
    onGoStart: () => setActiveTab("start"),
    onGoPipeline: () => {
      setActiveTab("pipeline");
      setPipelineSubTab("stage");
    },
    onGoStory: () => {
      setActiveTab("pipeline");
      setPipelineSubTab("story");
    },
    onGoProfile: () => {
      setActiveTab("pipeline");
      setPipelineSubTab("profile");
    },
    onScrollPreview: scrollPreview,
    jobCompleteAt,
    showToast,
  });

  const activeStepId = currentWorkflowStep(run);
  const activeIndex = workflowStepIndex(activeStepId);

  const navigateToStep = useCallback(
    (stepId: WorkflowStepId) => {
      const def = WORKFLOW_STEPS.find((s) => s.id === stepId);
      if (!def) return;
      if (stepId === "start") {
        setActiveTab("start");
        return;
      }
      if (!run) {
        showToast("Open an execution from the Executions tab first.");
        setActiveTab("executions");
        return;
      }
      setActiveTab("pipeline");
      setPipelineSubTab(def.subTab);
      const stageId = stageIdForStep(stepId, run);
      if (stageId) void selectStage(stageId);
      if (stepNeedsCheckpoint(stepId, run, apiGrants)) openActionModal();
      if (stepId === "ship") {
        requestAnimationFrame(() => {
          document.getElementById("workflow-deliverable")?.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
        });
      }
    },
    [run, apiGrants, setActiveTab, setPipelineSubTab, selectStage, openActionModal, showToast],
  );

  const operatorAction = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  const precleanWarnings = run?.job?.preclean_warnings;

  const openPendingInPipeline = () => {
    if (!run) return;
    setActiveTab("pipeline");
    if (operatorAction.mode !== "needs_you") return;
    invokeOperatorActionPrimary(operatorAction, {
      openModal: (sid, subId) => {
        if (sid) void selectStage(sid);
        if (subId) setActiveSubstepId(subId);
        openActionModal();
      },
      runStage: (sid) => void executeJob(executeBodyForStage(sid)),
      continueNext: () => void runNextStage(),
      viewLogs: () => scrollToLogs(),
    });
  };

  return (
    <header
      className={`live-status-bar kind-${live.activityKind}${statusOnlyOnPipeline ? " mode-status-only" : ""}`}
      data-testid="live-status-bar"
      role="status"
      aria-live="polite"
      aria-describedby={activeTab === "pipeline" ? "pipeline-step-context" : undefined}
    >
      <SessionBanner
        run={run}
        onReviewReuse={() => {
          setActiveTab("pipeline");
          setPipelineSubTab("stage");
        }}
      />
      <div className="live-status-main">
        <div className="live-status-headline-row">
          <span
            className={`live-status-dot kind-${live.activityKind}${live.activityKind === "running" ? " spinning" : ""}`}
            aria-hidden
          />
          <div className="live-status-headlines">
            <p className="live-status-headline">{live.headline}</p>
            {live.subline ? (
              <p className="live-status-subline muted" title={live.subline}>
                {live.subline}
              </p>
            ) : null}
          </div>
          <div className="live-status-actions">
            {live.errorCount > 0 ? (
              <button
                type="button"
                className="btn ghost sm live-status-error-chip"
                onClick={() => {
                  setLogFilterPreset({ level: "error", stream: "all", scrollToError: true });
                  setActiveTab("logs");
                }}
              >
                {live.errorCount} error{live.errorCount === 1 ? "" : "s"}
              </button>
            ) : null}
            {activeTab !== "pipeline" && pendingActionCount > 0 && operatorAction.mode === "needs_you" ? (
              <button
                type="button"
                className="btn ghost sm"
                onClick={openPendingInPipeline}
                title={operatorAction.subline ?? operatorAction.headline}
              >
                Open step in Pipeline ({pendingActionCount})
              </button>
            ) : null}
            {(run?.journey?.pending_write_stages || []).length > 0 &&
            run?.journey?.first_try?.write_approval_deferred ? (
              <button
                type="button"
                className="btn primary sm"
                data-action-id="gui.write_approval.batch_save"
                data-testid="live-status-batch-save"
                disabled={!sessionReady || jobRunning || actionBusy}
                onClick={() => void approveBatchWrites()}
              >
                Save all pending ({run.journey.pending_write_stages.length})
              </button>
            ) : null}
            {live.primaryLabel && live.onPrimary && !statusOnlyOnPipeline ? (
              <button
                type="button"
                className="btn primary sm"
                data-testid="live-status-primary"
                disabled={live.primaryDisabled || !sessionReady || jobRunning || actionBusy}
                onClick={live.onPrimary}
              >
                {live.primaryLabel}
              </button>
            ) : null}
            {live.activityKind === "running" && live.onPrimary ? (
              <button type="button" className="btn ghost sm" onClick={live.onPrimary}>
                View logs
              </button>
            ) : null}
            <div className="live-status-menu-actions">
              <button
                type="button"
                className={`btn ghost sm${alertsMuted ? " muted-active" : ""}`}
                onClick={() => setAlertsMuted(!alertsMuted)}
              >
                {alertsMuted ? "Unmute" : "Mute"}
              </button>
              <div className="header-menu-wrap">
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => setMenuOpen(!menuOpen)}
                  aria-expanded={menuOpen}
                >
                  Menu
                </button>
                {menuOpen ? (
                  <div className="header-menu panel">
                    <button
                      type="button"
                      className="btn ghost sm block"
                      onClick={() => {
                        setActiveTab("logs");
                        setMenuOpen(false);
                      }}
                    >
                      View full log
                    </button>
                    <button
                      type="button"
                      className="btn danger ghost sm block"
                      disabled={!sessionReady}
                      onClick={() => void clearSession()}
                    >
                      Clear session
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {live.jobProgress ? (
          <div className="live-status-progress" aria-hidden>
            <div
              className="live-status-progress-fill"
              style={{
                width: `${Math.round(
                  (live.jobProgress.index / live.jobProgress.total) * 100,
                )}%`,
              }}
            />
          </div>
        ) : null}

        <div className="live-status-phase-row">
          <span
            className="live-status-phase-label muted"
            title="High-level journey: Prepare → Export. Individual pipeline steps are numbered separately in the Pipeline tab."
          >
            Workflow phase {activeIndex + 1} of {WORKFLOW_STEPS.length}:{" "}
            <strong>{WORKFLOW_STEPS[activeIndex]?.label}</strong>
          </span>
          <ol
            className={`workflow-step-track live-status-chips${activeTab === "pipeline" ? " workflow-phase-bar-readonly" : ""}`}
          >
            {WORKFLOW_STEPS.map((step, i) => {
              const status = workflowStepStatus(step.id, run, apiGrants);
              const isActive = step.id === activeStepId;
              const attentionCount = workflowStepAttentionCount(step.id, run, apiGrants);
              const isRunningChip = isActive && live.activityKind === "running";
              const readonlyPhase = activeTab === "pipeline";
              const chipClass = `workflow-step-chip status-${status}${isActive ? " current" : ""}${isRunningChip ? " running" : ""}`;
              return (
                <li key={step.id} className="workflow-step-item">
                  {i > 0 ? (
                    <span className="workflow-step-connector" aria-hidden />
                  ) : null}
                  {readonlyPhase ? (
                    <span className={chipClass} title={step.tooltip}>
                      {isRunningChip ? (
                        <span className="spinner-inline workflow-chip-spinner" aria-hidden />
                      ) : null}
                      {status === "done" ? (
                        <span className="workflow-step-check">✓</span>
                      ) : null}
                      {step.label}
                    </span>
                  ) : (
                    <button
                      type="button"
                      className={chipClass}
                      title={step.tooltip}
                      aria-current={isActive ? "step" : undefined}
                      onClick={() => navigateToStep(step.id)}
                    >
                      {isRunningChip ? (
                        <span className="spinner-inline workflow-chip-spinner" aria-hidden />
                      ) : null}
                      {status === "done" ? (
                        <span className="workflow-step-check">✓</span>
                      ) : status === "attention" ? (
                        <span className="workflow-step-attention-dot" aria-hidden>
                          ●
                        </span>
                      ) : null}
                      {step.label}
                      {attentionCount > 0 ? (
                        <span className="workflow-step-attention-count">{attentionCount}</span>
                      ) : null}
                    </button>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
        {run && run.journey?.phase !== "ship" && activeTab !== "pipeline" ? (
          <PreviewListenPromo compact />
        ) : null}
      </div>

      {precleanWarnings?.length ? (
        <div className="preclean-warnings-banner compact-banner" role="status">
          {precleanWarnings
            .map((w) => `Pre-clean (${w.checkpoint}) — ${w.stage}`)
            .join(" · ")}
        </div>
      ) : null}

      {live.lastError?.traceback_excerpt ? (
        <details className="live-status-error-detail panel-inset">
          <summary>Error detail</summary>
          <pre>{live.lastError.traceback_excerpt}</pre>
        </details>
      ) : null}
    </header>
  );
}
