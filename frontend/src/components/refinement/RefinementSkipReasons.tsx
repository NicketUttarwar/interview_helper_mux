import type { RefinementPlan } from "../../types";
import { refinementReasonLabel } from "../../utils/refinementLabels";

interface Props {
  plan?: RefinementPlan | null;
}

/** Reason codes for refine stages the L1 gate decided to skip — see refinement_gate.py. */
export function RefinementSkipReasons({ plan }: Props) {
  const skipped = (plan?.passes || []).filter((p) => p.status === "skip");
  if (!skipped.length) return null;

  return (
    <div className="refinement-skip-reasons" data-testid="refinement-skip-reasons">
      <h5 className="refinement-subsection-title">Skipped refinement passes</h5>
      <ul className="refinement-skip-list">
        {skipped.map((p) => (
          <li key={p.pass_id} className="refinement-skip-row">
            <span className="refinement-skip-pass">{p.pass_id.replace(/_/g, " ")}</span>
            <span className="hint sm refinement-skip-reason">
              {p.reason_code ? refinementReasonLabel(p.reason_code) : p.rationale || "skipped"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
