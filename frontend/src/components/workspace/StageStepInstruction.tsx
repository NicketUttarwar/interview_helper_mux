import type { StageStep } from "../../types";

interface Props {
  step: StageStep;
}

export function StageStepInstruction({ step }: Props) {
  return (
    <div className="stage-step-instruction">
      {step.instruction ? <p className="stage-step-instruction-text">{step.instruction}</p> : null}
      {step.review?.length ? (
        <ul className="stage-step-review" data-testid={`stage-step-${step.id}-review`}>
          {step.review.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {step.next_hint ? <p className="stage-step-next-hint hint sm">{step.next_hint}</p> : null}
    </div>
  );
}
