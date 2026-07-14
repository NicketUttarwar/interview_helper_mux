import type { StageInfo, StageStep } from "../../types";
import { ActionMarker } from "../guidance/ActionMarker";
import { StageStepInstruction } from "./StageStepInstruction";
import { StageStepBody } from "./StageStepBody";
import { StageStepFooter } from "./StageStepFooter";
import { isAutoNavConsumed } from "../../utils/autoNavigationLedger";

interface Props {
  step: StageStep;
  stage: StageInfo;
  isActive: boolean;
  onActivate: () => void;
}

function stepMarkerStatus(step: StageStep): "todo" | "done" | "waiting" {
  if (step.status === "done") return "done";
  if (step.status === "waiting" || step.status === "blocked") return "waiting";
  return "todo";
}

export function StageStepRow({ step, stage, isActive, onActivate }: Props) {
  const autoGuided = isAutoNavConsumed({ stageId: stage.id, stepId: step.id });

  return (
    <section
      id={`stage-step-${step.id}`}
      className={`stage-step-row${isActive ? " stage-step-row--active" : ""}${step.status === "done" ? " stage-step-row--done" : ""}${isActive && (step.kind === "reuse" || step.kind === "write_approval") ? " stage-step-row--decision" : ""}${autoGuided ? " stage-step-row--auto-guided" : ""}`}
      data-testid={`stage-step-${step.id}`}
    >
      <button
        type="button"
        className="stage-step-row-header"
        onClick={onActivate}
        aria-expanded={isActive}
      >
        <span className="stage-step-number">{step.number}</span>
        <ActionMarker status={stepMarkerStatus(step)} />
        <span className="stage-step-label">
          {step.label}
          {autoGuided ? (
            <span
              className="stage-step-auto-guided-badge"
              title="Auto-opened once this server session — browse freely without being sent back"
            >
              guided
            </span>
          ) : null}
        </span>
        <span className={`stage-step-status-chip status-${step.status}`}>{step.status}</span>
      </button>
      {isActive ? (
        <div className="stage-step-body">
          <StageStepInstruction step={step} />
          <StageStepBody step={step} stage={stage} />
          <StageStepFooter step={step} stage={stage} isActive={isActive} />
        </div>
      ) : null}
    </section>
  );
}
