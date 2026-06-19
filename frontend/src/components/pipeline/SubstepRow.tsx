import type { StageSubstep } from "../../types";
import { ActionMarker } from "../guidance/ActionMarker";

interface Props {
  substep: StageSubstep;
  onClick?: () => void;
  selected?: boolean;
  compact?: boolean;
}

export function SubstepRow({ substep, onClick, selected, compact }: Props) {
  const clickable = substep.status === "todo" || substep.status === "running";
  const Tag = clickable ? "button" : "div";

  return (
    <Tag
      type={clickable ? "button" : undefined}
      className={`pipeline-substep-row status-${substep.status}${selected ? " selected" : ""}${compact ? " compact" : ""}`}
      data-testid={`substep-${substep.id}`}
      aria-current={selected ? "step" : undefined}
      aria-busy={substep.status === "running" ? true : undefined}
      onClick={clickable ? onClick : undefined}
      disabled={!clickable}
    >
      {substep.status === "running" ? (
        <span className="spinner-inline pipeline-substep-spinner" aria-hidden />
      ) : (
        <ActionMarker status={substep.status === "done" ? "done" : substep.status === "waiting" ? "waiting" : "todo"} />
      )}
      <span className="pipeline-substep-label">{substep.label}</span>
      {substep.primaryLabel && substep.status === "todo" && !compact ? (
        <span className="pipeline-substep-action muted">{substep.primaryLabel}</span>
      ) : null}
    </Tag>
  );
}
