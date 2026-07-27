import type { RefinementCascade, RefinementEvidencePacketRef } from "../../types";

interface Props {
  evidencePackets?: RefinementEvidencePacketRef[];
  cascade?: RefinementCascade | null;
  onOpen: (path: string) => void;
}

/** Read-only evidence packet links (opened via the existing file editor) plus a cascade summary. */
export function RefinementEvidencePanel({ evidencePackets, cascade, onOpen }: Props) {
  const packets = evidencePackets || [];
  if (!packets.length && !cascade) return null;

  return (
    <div className="refinement-evidence-panel" data-testid="refinement-evidence-panel">
      {packets.length ? (
        <>
          <h5 className="refinement-subsection-title">Evidence packets</h5>
          <ul className="refinement-evidence-list">
            {packets.map((p) => (
              <li key={p.path} className="refinement-evidence-row">
                <span className="refinement-evidence-pass">{p.pass_id}</span>
                <code className="artifact-path">{p.path}</code>
                <button type="button" className="btn ghost sm" onClick={() => onOpen(p.path)}>
                  Open
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {cascade ? (
        <div className="refinement-cascade-summary">
          <h5 className="refinement-subsection-title">Downstream cascade</h5>
          <p className="hint sm">
            {cascade.line_ids_changed?.length
              ? `${cascade.line_ids_changed.length} line(s) changed`
              : "No lines changed"}
            {cascade.line_ids_dropped?.length
              ? `, ${cascade.line_ids_dropped.length} dropped`
              : ""}
            {cascade.remix_after_edl ? " — remix required after EDL." : "."}
          </p>
          {cascade.stages_to_invalidate?.length ? (
            <p className="hint sm">
              Stages flagged for re-run: <strong>{cascade.stages_to_invalidate.join(", ")}</strong>
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
