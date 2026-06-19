import { useCallback, useMemo } from "react";
import { useApp } from "../context/AppContext";
import { useLiveStatus } from "../hooks/useLiveStatus";
import { resolvePendingAction } from "../utils/pendingAction";
import { countRequiredAttention } from "../utils/attentionQueue";
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
    selectStage,
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
  } = useApp();

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
    selectedStageId,
    logEntries,
    apiGrants,
    onExecute: (body) => void executeJob(body),
    onRunNext: () => void runNextStage(),
    onOpenCheckpoint: (stageId) => {
      if (stageId) void selectStage(stageId);
      openActionModal();
    },
    onAcknowledgeHandoff: () => void acknowledgeHandoff(),
    onApproveWrite: (stageId) => void approveWriteAndContinue(stageId),
    onGoLogs: () => {
      setLogFilterPreset({ stream: "live" });
      setActiveTab("logs");
    },
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

  const precleanWarnings = run?.job?.preclean_warnings;
  const pendingAction = useMemo(
    () => resolvePendingAction(run, apiGrants),
    [run, apiGrants],
  );
  const requiredCount = useMemo(
    () => countRequiredAttention(run, apiGrants),
    [run, apiGrants],
  );

  const onActionBadgeClick = () => {
    if (requiredCount > 1) {
      setActiveTab("pipeline");
      setPipelineSubTab("stage");
      requestAnimationFrame(() => {
        document.querySelector(".attention-queue-panel")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
      return;
    }
    openActionModal();
  };

  const headline =
    live.primaryLabel && live.primaryLabel === run?.journey?.next_action
      ? live.primaryLabel
      : live.headline;
  const subline =
    live.primaryLabel && live.primaryLabel === run?.journey?.next_action
      ? live.headline
      : live.subline;

  return (
    <header
      className={`live-status-bar kind-${live.activityKind}`}
      data-testid="live-status-bar"
      role="status"
      aria-live="polite"
    >
      <div className="live-status-main">
        <div className="live-status-headline-row">
          <span className={`live-status-dot kind-${live.activityKind}`} aria-hidden />
          <div className="live-status-headlines">
            <p className="live-status-headline">{headline}</p>
            {subline ? (
              <p className="live-status-subline muted" title={subline}>
                {subline}
              </p>
            ) : null}
          </div>
          <div className="live-status-actions">
            {live.errorCount > 0 ? (
              <button
                type="button"
                className="btn ghost sm live-status-error-chip"
                onClick={() => {
                  setLogFilterPreset({ level: "error", stream: "all" });
                  setActiveTab("logs");
                }}
              >
                {live.errorCount} error{live.errorCount === 1 ? "" : "s"}
              </button>
            ) : null}
            {pendingActionCount > 0 ? (
              <button
                type="button"
                className="btn primary sm action-badge-btn"
                onClick={onActionBadgeClick}
                title={pendingAction?.message}
              >
                {pendingAction?.primaryLabel || "Action"} ({pendingActionCount})
              </button>
            ) : null}
            {live.secondaryLabel && live.onSecondary ? (
              <button type="button" className="btn ghost sm" onClick={live.onSecondary}>
                {live.secondaryLabel}
              </button>
            ) : null}
            {live.primaryLabel && live.onPrimary ? (
              <button
                type="button"
                className="btn primary sm"
                data-testid="live-status-primary"
                disabled={live.primaryDisabled || !sessionReady}
                onClick={live.onPrimary}
              >
                {live.primaryLabel}
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
          <ol className="workflow-step-track live-status-chips">
            {WORKFLOW_STEPS.map((step, i) => {
              const status = workflowStepStatus(step.id, run, apiGrants);
              const isActive = step.id === activeStepId;
              const attentionCount = workflowStepAttentionCount(step.id, run, apiGrants);
              const prog =
                step.id !== "start" &&
                run?.journey?.phase_progress?.[step.id as keyof typeof run.journey.phase_progress];
              const progressHint =
                prog && prog.total > 0 ? ` · ${prog.done}/${prog.total}` : "";
              const attentionHint =
                attentionCount > 0 ? ` · ${attentionCount} need you` : "";
              return (
                <li key={step.id} className="workflow-step-item">
                  {i > 0 ? (
                    <span className="workflow-step-connector" aria-hidden />
                  ) : null}
                  <button
                    type="button"
                    className={`workflow-step-chip status-${status}${isActive ? " current" : ""}`}
                    title={`${step.tooltip}${progressHint}${attentionHint}`}
                    aria-current={isActive ? "step" : undefined}
                    onClick={() => navigateToStep(step.id)}
                  >
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
                </li>
              );
            })}
          </ol>
        </div>
        {run && run.journey?.phase !== "ship" ? (
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
