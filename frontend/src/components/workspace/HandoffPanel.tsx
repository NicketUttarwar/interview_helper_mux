import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { getHandoffPathsLocal } from "../../utils/checkpoint";
import { findLatestHandoffAudit } from "../../utils/handoff";
import { handoffSkimBullets } from "../../utils/handoffSkimHints";
import { escapeHtml } from "../../utils";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";

export function HandoffPanel() {
  const { run, selectedStage, acknowledgeHandoff, openArtifactInEditor, actionBusy } =
    useApp();

  const { paths, audit, visible, skimBullets } = useMemo(() => {
    if (!run || !selectedStage) {
      return { paths: [], audit: null, visible: false, skimBullets: [] as string[] };
    }
    const paths = getHandoffPathsLocal(selectedStage, run.log_tail);
    const audit = findLatestHandoffAudit(selectedStage.id, run.log_tail);
    const skimBullets = handoffSkimBullets(paths, selectedStage);
    return { paths, audit, visible: paths.length > 0 || Boolean(audit), skimBullets };
  }, [run, selectedStage]);

  if (!visible || !selectedStage || !run) return null;

  const handoffAcked = Boolean(run.handoff_ack?.[selectedStage.id]);

  const editableSet = new Set(selectedStage.editable || []);

  if (handoffAcked) {
    return (
      <div className="panel handoff-panel handoff-panel--done" id="stage-handoff-panel">
        <StepDoneBanner variant="substep" title="Handoff acknowledged — step complete" />
      </div>
    );
  }

  return (
    <div className="panel handoff-panel attention-required" id="stage-handoff-panel">
      <div className="panel-head">
        <h3>Review AI-generated outputs</h3>
      </div>
      <p className="hint sm">
        Skim the files below. Edit in Files if needed. Acknowledge when ready for the next
        automated step.
      </p>
      {skimBullets.length ? (
        <ul className="handoff-skim-list">
          {skimBullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      ) : null}
      <ul className="handoff-list">
        {paths.map((p) => (
          <li key={p} className="handoff-item">
            <code>{escapeHtml(p)}</code>{" "}
            {editableSet.has(p) ? <span className="hint">editable</span> : null}
            <span className="handoff-actions">
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => openArtifactInEditor(p)}
              >
                Open in Files
              </button>
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  void navigator.clipboard?.writeText(p);
                }}
              >
                Copy path
              </button>
            </span>
          </li>
        ))}
        {audit ? (
          <li className="handoff-item muted">
            LLM audit: <code>{escapeHtml(audit)}</code>
          </li>
        ) : null}
      </ul>
      <div className="handoff-footer">
        <button
          type="button"
          className="btn primary sm"
          data-testid="handoff-acknowledge"
          disabled={actionBusy}
          onClick={() => void acknowledgeHandoff()}
        >
          Acknowledge &amp; continue
        </button>
      </div>
    </div>
  );
}
