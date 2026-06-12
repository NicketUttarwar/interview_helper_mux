import { useCallback, useMemo } from "react";
import { useApp } from "../context/AppContext";
import { useLiveStatus } from "../hooks/useLiveStatus";
import { SourceAudioHashBadge } from "./guidance/SourceAudioHashBadge";
import { formatTs } from "../utils";
import {
  WORKFLOW_STEPS,
  currentWorkflowStep,
  stageIdForStep,
  stepNeedsCheckpoint,
  workflowStepIndex,
  workflowStepStatus,
  type WorkflowStepId,
} from "../utils/workflowSteps";
import type { OperatorPhase } from "../types";

export function LiveStatusBar() {
  const {
    run,
    jobRunning,
    selectedStageId,
    logEntries,
    apiGrants,
    executeJob,
    openActionModal,
    acknowledgeHandoff,
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
  } = useApp();

  const live = useLiveStatus(run, {
    jobRunning,
    selectedStageId,
    logEntries,
    apiGrants,
    onExecute: (body) => void executeJob(body),
    onOpenCheckpoint: (stageId) => {
      if (stageId) void selectStage(stageId);
      openActionModal();
    },
    onAcknowledgeHandoff: () => void acknowledgeHandoff(),
    onGoLogs: () => {
      setLogFilterPreset({ stream: "live" });
      setActiveTab("logs");
    },
    onGoStart: () => setActiveTab("start"),
    onGoPipeline: () => {
      setActiveTab("pipeline");
      setPipelineSubTab("stage");
    },
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
      if (stepNeedsCheckpoint(stepId, run)) openActionModal();
      if (stepId === "ship") {
        requestAnimationFrame(() => {
          document.getElementById("workflow-deliverable")?.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
        });
      }
    },
    [run, setActiveTab, setPipelineSubTab, selectStage, openActionModal, showToast],
  );

  const precleanWarnings = run?.job?.preclean_warnings;
  const unseenErrors = useMemo(() => {
    if (live.activityKind === "error") return live.errorCount;
    return live.errorCount;
  }, [live]);

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
            <p className="live-status-headline">{live.headline}</p>
            {live.subline ? (
              <p className="live-status-subline muted" title={live.subline}>
                {live.subline}
              </p>
            ) : null}
          </div>
          <div className="live-status-actions">
            {unseenErrors > 0 ? (
              <button
                type="button"
                className="btn ghost sm live-status-error-chip"
                onClick={() => {
                  setLogFilterPreset({ level: "error", stream: "all" });
                  setActiveTab("logs");
                }}
              >
                {unseenErrors} error{unseenErrors === 1 ? "" : "s"}
              </button>
            ) : null}
            {pendingActionCount > 0 ? (
              <button
                type="button"
                className="btn primary sm action-badge-btn"
                onClick={openActionModal}
              >
                Action ({pendingActionCount})
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
          <span className="live-status-phase-label muted">
            Phase {activeIndex + 1} of {WORKFLOW_STEPS.length}:{" "}
            <strong>{WORKFLOW_STEPS[activeIndex]?.label}</strong>
          </span>
          <ol className="workflow-step-track live-status-chips">
            {WORKFLOW_STEPS.map((step, i) => {
              const status = workflowStepStatus(step.id, run);
              const isActive = step.id === activeStepId;
              const prog =
                step.id !== "start" &&
                run?.journey?.phase_progress?.[step.id as OperatorPhase];
              const progressHint =
                prog && prog.total > 0 ? ` · ${prog.done}/${prog.total}` : "";
              return (
                <li key={step.id} className="workflow-step-item">
                  {i > 0 ? (
                    <span className="workflow-step-connector" aria-hidden />
                  ) : null}
                  <button
                    type="button"
                    className={`workflow-step-chip status-${status}${isActive ? " current" : ""}`}
                    title={`${step.tooltip}${progressHint}`}
                    aria-current={isActive ? "step" : undefined}
                    onClick={() => navigateToStep(step.id)}
                  >
                    {status === "done" ? (
                      <span className="workflow-step-check">✓</span>
                    ) : null}
                    {step.label}
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="live-status-meta status-grid status-grid-compact">
          <div className="status-cell">
            <span className="status-label">Run</span>
            <span className="status-value">
              {run?.meta?.execution_number
                ? `#${run.meta.execution_number}`
                : run?.run_id || "None"}
            </span>
          </div>
          <div className="status-cell">
            <span className="status-label">Source</span>
            <span
              className="status-value muted source-lock-label"
              title={run?.meta?.input_audio_path}
            >
              {run?.meta?.input_audio_path
                ? `${run.meta.input_audio_path.split("/").pop()} (locked)`
                : "—"}
            </span>
          </div>
          {run?.meta?.source_audio_hash_short ? (
            <div className="status-cell status-cell-hash">
              <span className="status-label">Hash</span>
              <SourceAudioHashBadge
                hashShort={run.meta.source_audio_hash_short}
                hashFull={run.meta.source_audio_hash}
                label=""
              />
            </div>
          ) : null}
          <div className="status-cell">
            <span className="status-label">Updated</span>
            <span className="status-value muted">{formatTs(run?.meta?.updated_at)}</span>
          </div>
          <div className="status-cell actions">
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
