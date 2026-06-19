import type { OperatorPhase, RunData } from "../../types";
import { PHASE_LABELS, phaseLabel } from "../../constants/phases";
import { ActionMarker } from "./ActionMarker";
import { GuidanceActionButton } from "./GuidanceActionButton";
import { SubstepRow } from "../pipeline/SubstepRow";
import { guidanceItemToSubstep } from "../../utils/stageSubsteps";
import { useApp } from "../../context/AppContext";
import { WORKFLOW_STEPS } from "../../utils/workflowSteps";
import { isPhaseFullyComplete } from "../../utils/phaseSubsteps";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";

interface Props {
  run: RunData;
  compact?: boolean;
}

export function PhaseGuidanceBanner({ run, compact }: Props) {
  const phase = run.journey?.phase ?? "prepare";
  const phaseGuidance = run.journey?.phase_guidance?.[phase];
  const flowNote = run.display_flow || run.selected_flow || run.journey?.flow_intent;
  const blocking = run.journey?.blocking ?? run.blocking;

  const goal =
    phaseGuidance?.goal ||
    WORKFLOW_STEPS.find((s) => s.id === phase)?.tooltip ||
    "";

  const progress = phaseGuidance?.progress || run.journey?.phase_progress?.[phase];
  const actions = (phaseGuidance?.actions || []).slice(0, compact ? 2 : 3);
  const phaseComplete = isPhaseFullyComplete(run, phase);

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
        {flowNote && phase === "create" ? (
          <p className="hint sm">Showing {String(flowNote).replace("flow", "Flow ")} stages</p>
        ) : null}
      </div>
      {goal ? <p className="hint phase-guidance-goal">{goal}</p> : null}
      {blocking?.blocked && blocking.message ? (
        <ul className="stage-guidance-list phase-guidance-actions">
          <li className="stage-guidance-item status-todo">
            <ActionMarker status="todo" />
            <span className="stage-guidance-label">{blocking.message}</span>
            <GuidanceActionButton
              item={{
                id: "blocking",
                label: blocking.message,
                status: "todo",
                kind: "checkpoint",
                stage_id: blocking.stage_id || undefined,
              }}
            />
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
              <GuidanceActionButton item={item} />
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
  const { activateSubstep } = useApp();
  const item = {
    id: "pick_audio",
    label: "Pick source audio on the Start tab",
    status: "todo" as const,
    kind: "start",
  };
  const startSubstep = guidanceItemToSubstep(item, "start");
  return (
    <section className="phase-guidance-banner panel-inset" aria-label="Start guidance">
      <h3 className="phase-guidance-title">Start</h3>
      <p className="hint phase-guidance-goal">Pick source audio and optionally set your output type.</p>
      <ul className="pipeline-substeps start-phase-substeps">
        <li>
          <SubstepRow substep={startSubstep} onClick={() => activateSubstep(startSubstep)} />
        </li>
      </ul>
    </section>
  );
}

export function phaseLabelForOperatorPhase(phase: OperatorPhase | "start"): string {
  return phaseLabel(phase);
}
