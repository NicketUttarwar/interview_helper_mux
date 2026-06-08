import type { OperatorPhase, RunData } from "../../types";
import { ActionMarker } from "./ActionMarker";
import { GuidanceActionButton } from "./GuidanceActionButton";
import { WORKFLOW_STEPS } from "../../utils/workflowSteps";

const PHASE_LABELS: Record<string, string> = {
  start: "Start",
  prepare: "Prepare",
  understand: "Analyze",
  complete: "Complete",
  create: "Build",
  polish: "Sound",
  ship: "Export",
};

interface Props {
  run: RunData;
}

export function PhaseGuidanceBanner({ run }: Props) {
  const phase = run.journey?.phase ?? "prepare";
  const phaseGuidance = run.journey?.phase_guidance?.[phase];
  const flowNote = run.display_flow || run.selected_flow || run.journey?.flow_intent;

  const goal =
    phaseGuidance?.goal ||
    WORKFLOW_STEPS.find((s) => s.id === phase)?.tooltip ||
    "";

  const progress = phaseGuidance?.progress || run.journey?.phase_progress?.[phase];
  const actions = phaseGuidance?.actions || [];

  return (
    <section className="phase-guidance-banner panel-inset" aria-label="Phase guidance">
      <div className="phase-guidance-head">
        <h3 className="phase-guidance-title">
          {PHASE_LABELS[phase] || phase} phase
          {progress && progress.total > 0 ? (
            <span className="phase-guidance-progress muted">
              · {progress.done}/{progress.total} steps done
            </span>
          ) : null}
        </h3>
        {flowNote && phase === "create" ? (
          <p className="hint sm">Showing {String(flowNote).replace("flow", "Flow ")} stages</p>
        ) : null}
      </div>
      {goal ? <p className="hint phase-guidance-goal">{goal}</p> : null}
      {actions.length > 0 ? (
        <ul className="stage-guidance-list phase-guidance-actions">
          {actions.map((item) => (
            <li key={`${item.from_stage_id || ""}-${item.id}`} className={`stage-guidance-item status-${item.status}`}>
              <ActionMarker status={item.status} />
              <span className="stage-guidance-label">
                {item.from_stage_title ? `${item.from_stage_title}: ` : ""}
                {item.label}
              </span>
              <GuidanceActionButton item={item} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function StartPhaseGuidance() {
  const startGuidance = {
    id: "pick_audio",
    label: "Pick source audio on the Start tab",
    status: "todo" as const,
    kind: "start",
  };
  return (
    <section className="phase-guidance-banner panel-inset" aria-label="Start guidance">
      <h3 className="phase-guidance-title">Start</h3>
      <p className="hint phase-guidance-goal">Pick source audio and optionally set your output type.</p>
      <ul className="stage-guidance-list">
        <li className="stage-guidance-item status-todo">
          <ActionMarker status="todo" />
          <span className="stage-guidance-label">{startGuidance.label}</span>
          <GuidanceActionButton item={startGuidance} />
        </li>
      </ul>
    </section>
  );
}

export function phaseLabelForOperatorPhase(phase: OperatorPhase | "start"): string {
  return PHASE_LABELS[phase] || phase;
}
