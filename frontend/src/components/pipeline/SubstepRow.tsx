import type { StageSubstep } from "../../types";
import { ActionMarker } from "../guidance/ActionMarker";

interface Props {
  substep: StageSubstep;
  onClick?: () => void;
  onSkip?: () => void;
  selected?: boolean;
  compact?: boolean;
}

export function SubstepRow({ substep, onClick, onSkip, selected, compact }: Props) {
  const isError = substep.status === "error";
  const showSkip = substep.id === "optional:skip" && substep.status === "todo" && onSkip;
  const clickable =
    (substep.status === "todo" || substep.status === "running" || isError) && !showSkip;
  const Tag = showSkip ? "div" : clickable ? "button" : "div";

  return (
    <Tag
      type={clickable ? "button" : undefined}
      className={`pipeline-substep-row substep-row--${substep.status} kind-${substep.kind} status-${substep.status}${isError ? " substep-row--error" : ""}${selected ? " selected" : ""}${compact ? " compact" : ""}`}
      data-testid={`substep-${substep.id}`}
      tabIndex={clickable ? (selected ? 0 : -1) : undefined}
      aria-current={selected ? "step" : undefined}
      aria-busy={substep.status === "running" && substep.kind === "run" ? true : undefined}
      onClick={clickable ? onClick : undefined}
      disabled={clickable ? false : undefined}
    >
      {substep.status === "running" &&
      (substep.kind === "run" || substep.kind === "write_approval") ? (
        <span className="spinner-inline pipeline-substep-spinner" aria-hidden />
      ) : isError ? (
        <span className="log-level-dot level-error" aria-hidden />
      ) : (
        <ActionMarker
          status={
            substep.status === "done"
              ? "done"
              : substep.status === "waiting"
                ? "waiting"
                : "todo"
          }
        />
      )}
      <span className="pipeline-substep-label">{substep.label}</span>
      {showSkip ? (
        <button
          type="button"
          className="btn link sm substep-skip-btn"
          onClick={(e) => {
            e.stopPropagation();
            onSkip?.();
          }}
        >
          Skip
        </button>
      ) : null}
    </Tag>
  );
}
