import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { getHandoffPathsLocal } from "../../utils/checkpoint";
import { findLatestHandoffAudit } from "../../utils/handoff";
import { escapeHtml } from "../../utils";

export function HandoffPanel() {
  const { run, selectedStage, acknowledgeHandoff, openArtifactInEditor } = useApp();

  const { paths, audit, visible } = useMemo(() => {
    if (!run || !selectedStage) return { paths: [], audit: null, visible: false };
    const paths = getHandoffPathsLocal(selectedStage, run.log_tail);
    const audit = findLatestHandoffAudit(selectedStage.id, run.log_tail);
    return { paths, audit, visible: paths.length > 0 || Boolean(audit) };
  }, [run, selectedStage]);

  if (!visible || !selectedStage) return null;

  const editableSet = new Set(selectedStage.editable || []);

  return (
    <div className="panel handoff-panel">
      <div className="panel-head">
        <h3>Review AI-generated outputs</h3>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => void acknowledgeHandoff()}
        >
          Acknowledge &amp; continue
        </button>
      </div>
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
                Open
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
    </div>
  );
}
