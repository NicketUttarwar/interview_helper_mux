import { useState } from "react";
import type { OperatorPhase, RunData } from "../../types";
import { PHASE_LABELS, phaseLabel } from "../../constants/phases";
import { ActionMarker } from "./ActionMarker";
import { useApp } from "../../context/AppContext";
import { WORKFLOW_STEPS } from "../../utils/workflowSteps";
import { isPhaseFullyComplete } from "../../utils/phaseSubsteps";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";
import { firstTodoStepId } from "../../utils/resolveActiveStep";
import { api } from "../../api/client";

interface Props {
  run: RunData;
  compact?: boolean;
}

export function PhaseGuidanceBanner({ run, compact }: Props) {
  const { setActiveTab, selectStage, setActiveStepId, refreshRun } = useApp();
  const phase = run.journey?.phase ?? "prepare";
  const phaseGuidance = run.journey?.phase_guidance?.[phase];
  const blocking = run.journey?.blocking ?? run.blocking;
  const escalations = run.resilience?.open_escalations || [];
  const [busy, setBusy] = useState<string | null>(null);

  const goal =
    phaseGuidance?.goal ||
    WORKFLOW_STEPS.find((s) => s.id === phase)?.tooltip ||
    "";

  const progress = phaseGuidance?.progress || run.journey?.phase_progress?.[phase];
  const actions = (phaseGuidance?.actions || []).slice(0, compact ? 2 : 3);
  const phaseComplete = isPhaseFullyComplete(run, phase);

  const goToStage = (stageId?: string) => {
    if (!stageId) return;
    setActiveTab("pipeline");
    void selectStage(stageId);
    const stepId = firstTodoStepId(run, stageId);
    if (stepId) setActiveStepId(stepId);
  };

  const resolveEscalation = async (stageId: string, optionId: string) => {
    setBusy(`${stageId}:${optionId}`);
    try {
      await api(`/api/runs/${run.run_id}/escalations/${stageId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ chosen_option: optionId }),
      });
      await refreshRun();
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className={`phase-guidance-banner panel-inset${phaseComplete ? " phase-complete" : ""}`} aria-label="Phase guidance">
      {phaseComplete ? <StepDoneBanner variant="phase" title={`${PHASE_LABELS[phase] || phase} phase complete`} /> : null}
      <div className="phase-guidance-head">
        <h3 className="phase-guidance-title">
          {PHASE_LABELS[phase] || phase} phase
          {progress && progress.total > 0 ? (
            <span className="phase-guidance-progress muted">
              · {progress.done}/{progress.total} steps done
            </span>
          ) : null}
        </h3>
      </div>
      {goal ? <p className="hint phase-guidance-goal">{goal}</p> : null}
      {escalations.length > 0 ? (
        <ul className="stage-guidance-list phase-guidance-actions" aria-label="Open escalations">
          {escalations.slice(0, compact ? 1 : 3).map((esc) => (
            <li key={esc.stage_id} className="stage-guidance-item status-todo">
              <ActionMarker status="todo" />
              <span className="stage-guidance-label">
                Escalation ({esc.stage_id}): {esc.failed_invariant}
              </span>
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => goToStage(esc.resume_stage || esc.stage_id)}
              >
                Go to step
              </button>
              {(esc.options || []).slice(0, 2).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="btn sm"
                  disabled={busy === `${esc.stage_id}:${opt.id}`}
                  onClick={() => void resolveEscalation(esc.stage_id, opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </li>
          ))}
        </ul>
      ) : null}
      {blocking?.blocked && blocking.message ? (
        <ul className="stage-guidance-list phase-guidance-actions">
          <li className="stage-guidance-item status-todo">
            <ActionMarker status="todo" />
            <span className="stage-guidance-label">{blocking.message}</span>
            {blocking.stage_id ? (
              <button type="button" className="btn ghost sm" onClick={() => goToStage(blocking.stage_id || undefined)}>
                Go to step
              </button>
            ) : null}
          </li>
        </ul>
      ) : null}
      {actions.length > 0 ? (
        <ul className="stage-guidance-list phase-guidance-actions">
          {actions.map((item) => (
            <li
              key={`${item.from_stage_id || ""}-${item.id}`}
              className={`stage-guidance-item status-${item.status}`}
            >
              <ActionMarker status={item.status} />
              <span className="stage-guidance-label">
                {item.from_stage_title ? `${item.from_stage_title}: ` : ""}
                {item.label}
              </span>
              {item.stage_id || item.from_stage_id ? (
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => goToStage(item.stage_id || item.from_stage_id)}
                >
                  Go to step
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {compact && (phaseGuidance?.actions?.length || 0) > 2 ? (
        <p className="hint sm">More steps listed in the pipeline step list.</p>
      ) : null}
    </section>
  );
}

export function StartPhaseGuidance() {
  return (
    <section className="phase-guidance-banner panel-inset" aria-label="Start guidance">
      <h3 className="phase-guidance-title">Start</h3>
      <p className="hint phase-guidance-goal">Pick one interview WAV from ASSETS/ and click Start.</p>
      <ol className="hint sm start-phase-steps">
            <li>Select a WAV from ASSETS/</li>
            <li>Click Start on your chosen file</li>
      </ol>
    </section>
  );
}

export function phaseLabelForOperatorPhase(phase: OperatorPhase | "start"): string {
  return phaseLabel(phase);
}
