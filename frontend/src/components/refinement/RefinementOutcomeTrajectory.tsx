import type { ListenerOutcomeTrajectory } from "../../types";

interface Props {
  trajectory?: ListenerOutcomeTrajectory | null;
}

function formatPayload(payload: unknown): string | null {
  if (payload === null || payload === undefined) return null;
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload);
  } catch {
    return null;
  }
}

/** Milestone-by-milestone listener outcome snapshots — understanding/listener_outcome_trajectory.json. */
export function RefinementOutcomeTrajectory({ trajectory }: Props) {
  const points = trajectory?.points || [];
  if (!points.length) return null;

  return (
    <div className="refinement-outcome-trajectory" data-testid="refinement-outcome-trajectory">
      <h5 className="refinement-subsection-title">Listener outcome trajectory</h5>
      <ol className="refinement-outcome-list">
        {points.map((p, i) => {
          const detail = formatPayload(p.payload);
          return (
            <li key={`${p.milestone}-${i}`} className="refinement-outcome-row">
              <span className="refinement-outcome-milestone">{p.milestone}</span>
              {detail ? <span className="hint sm refinement-outcome-detail">{detail}</span> : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
