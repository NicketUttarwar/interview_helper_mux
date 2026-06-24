import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { getHandoffPathsLocal } from "../../utils/checkpoint";
import { findLatestHandoffAudit } from "../../utils/handoff";
import { handoffSkimBullets } from "../../utils/handoffSkimHints";
import { escapeHtml } from "../../utils";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";
import { useAsyncAction } from "../../hooks/useAsyncAction";

export function HandoffPanel() {
  const { run, selectedStage, acknowledgeHandoff, openArtifactInEditor, actionBusy, showToast } =
    useApp();
  const { busy: ackBusy, run: runAck } = useAsyncAction("handoff");

  const { paths, audit, skimBullets } = useMemo(() => {
    if (!run || !selectedStage) {
      return { paths: [] as string[], audit: null as string | null, skimBullets: [] as string[] };
    }
    const paths = getHandoffPathsLocal(selectedStage, run.log_tail);
    const audit = findLatestHandoffAudit(selectedStage.id, run.log_tail);
    const skimBullets = handoffSkimBullets(paths, selectedStage);
    return { paths, audit, skimBullets };
  }, [run, selectedStage]);

  if (!selectedStage || !run) return null;

  const handoffAcked = Boolean(run.handoff_ack?.[selectedStage.id]);
  const handoffPending =
    selectedStage.status === "done" &&
    !handoffAcked &&
    (paths.length > 0 ||
      Boolean(audit) ||
      run.journey?.blocking?.reason === "handoff_review");

  const onAck = () =>
    void runAck(() => acknowledgeHandoff(), {
      showToast,
      startMessage: "Acknowledging AI outputs…",
    });

  const ackDisabled = actionBusy || ackBusy;

  if (!handoffPending) {
    if (handoffAcked) {
      return (
        <div className="panel handoff-panel handoff-panel--done" id="stage-handoff-panel">
          <StepDoneBanner variant="substep" title="Handoff acknowledged — step complete" />
        </div>
      );
    }
    return null;
  }

  const editableSet = new Set(selectedStage.editable || []);

  if (!paths.length && !audit) {
    return (
      <div className="panel handoff-panel attention-required" id="stage-handoff-panel">
        <div className="panel-head">
          <h3>Review AI-generated outputs</h3>
        </div>
        <p className="hint sm">
          No output files were listed for this step. Acknowledge when ready for the next automated
          step.
        </p>
        <div className="handoff-footer">
          <button
            type="button"
            className="btn primary sm"
            data-testid="handoff-acknowledge"
            disabled={ackDisabled}
            onClick={onAck}
          >
            {ackBusy ? (
              <>
                <span className="spinner-inline" aria-hidden /> Acknowledging…
              </>
            ) : (
              "Acknowledge & continue"
            )}
          </button>
        </div>
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
                  showToast("Path copied.");
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
          disabled={ackDisabled}
          onClick={onAck}
        >
          {ackBusy ? (
            <>
              <span className="spinner-inline" aria-hidden /> Acknowledging…
            </>
          ) : (
            "Acknowledge & continue"
          )}
        </button>
      </div>
    </div>
  );
}
