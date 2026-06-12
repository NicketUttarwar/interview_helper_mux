import { useCallback } from "react";
import { useApp } from "../context/AppContext";
import { useOperatorCommand } from "../hooks/useOperatorCommand";
import { findHandoffStage } from "../utils/checkpoint";
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

/** Top workflow navigator — current step, clickable anchors, and next action. */
export function WorkflowStepBar() {
  const {
    run,
    jobRunning,
    executeJob,
    openActionModal,
    selectStage,
    acknowledgeHandoff,
    setActiveTab,
    setPipelineSubTab,
    showToast,
    sessionReady,
  } = useApp();

  const cmd = useOperatorCommand(run, {
    jobRunning,
    onExecute: (body) => void executeJob(body),
    onOpenCheckpoint: (stageId) => {
      if (stageId) void selectStage(stageId);
      openActionModal();
    },
    onAcknowledgeHandoff: () => {
      const hs = findHandoffStage(run);
      if (hs) void selectStage(hs.id).then(() => acknowledgeHandoff());
      else void acknowledgeHandoff();
    },
    onGoLogs: () => setActiveTab("logs"),
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

      if (run) {
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
      }
    },
    [run, setActiveTab, setPipelineSubTab, selectStage, openActionModal, showToast],
  );

  const stepLabel = WORKFLOW_STEPS[activeIndex]?.label ?? "Start";
  const statusShort =
    cmd.kind === "running"
      ? cmd.statusLine
      : cmd.kind === "no_run"
        ? "Pick audio to begin"
        : cmd.statusLine;

  return (
    <div
      className={`workflow-step-bar kind-${cmd.kind}`}
      role="navigation"
      aria-label="Workflow steps"
      data-testid="workflow-step-bar"
    >
      <div className="workflow-step-summary">
        <span className="workflow-step-current">
          Phase {activeIndex + 1} of {WORKFLOW_STEPS.length}: <strong>{stepLabel}</strong>
        </span>
        <span className="workflow-step-status muted">{statusShort}</span>
      </div>

      <ol className="workflow-step-track">
        {WORKFLOW_STEPS.map((step, i) => {
          const status = workflowStepStatus(step.id, run);
          const isActive = step.id === activeStepId;
          const prog =
            step.id !== "start" && run?.journey?.phase_progress?.[step.id as OperatorPhase];
          const progressHint =
            prog && prog.total > 0 ? ` · ${prog.done}/${prog.total} done` : "";
          return (
            <li key={step.id} className="workflow-step-item">
              {i > 0 ? <span className="workflow-step-connector" aria-hidden /> : null}
              <button
                type="button"
                className={`workflow-step-chip status-${status}${isActive ? " current" : ""}`}
                title={`${step.tooltip}${progressHint}`}
                aria-current={isActive ? "step" : undefined}
                onClick={() => navigateToStep(step.id)}
              >
                {status === "done" ? <span className="workflow-step-check">✓</span> : null}
                {step.label}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="workflow-step-actions">
        {cmd.secondaryLabel && cmd.onSecondary ? (
          <button
            type="button"
            className="btn ghost sm"
            data-testid="workflow-secondary"
            onClick={cmd.onSecondary}
          >
            {cmd.secondaryLabel}
          </button>
        ) : null}
        {cmd.primaryLabel && cmd.onPrimary ? (
          <button
            type="button"
            className="btn primary sm"
            data-testid="workflow-primary"
            disabled={cmd.primaryDisabled || !sessionReady}
            onClick={cmd.onPrimary}
          >
            {cmd.primaryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
