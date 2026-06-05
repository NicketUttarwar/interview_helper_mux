import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { useJourney } from "../../hooks/useJourney";

export function DeliverableCard() {
  const { run, runId, refreshRun, config } = useApp();
  const { deliverable, phase } = useJourney(run);
  const enabled = config?.journey_ui?.enabled !== false;

  if (!run || !enabled || !deliverable || deliverable.kind === "none") {
    return null;
  }

  const previewPath = deliverable.paths?.preview;
  const masterPath = deliverable.paths?.master;
  const descPath = deliverable.paths?.description;

  const playUrl = (rel: string) =>
    runId ? `/api/runs/${runId}/audio?path=${encodeURIComponent(rel)}` : "";

  const onPreviewListened = async () => {
    if (!runId) return;
    await api(`/api/runs/${runId}/milestones/preview-listened`, { method: "POST" });
    await refreshRun();
  };

  return (
    <footer id="workflow-deliverable" className="deliverable-card panel">
      <h4>Deliverable</h4>
      {previewPath && phase !== "ship" ? (
        <div className="deliverable-row">
          <span>Assembly preview</span>
          <audio controls src={playUrl(previewPath)} />
          <button type="button" className="btn ghost sm" onClick={() => void onPreviewListened()}>
            Continue to sound
          </button>
        </div>
      ) : null}
      {masterPath ? (
        <div className="deliverable-row">
          <span>Master</span>
          <audio controls src={playUrl(masterPath)} />
          {deliverable.qc_passed === false ? (
            <span className="deliverable-warn">QC check failed — see Logs</span>
          ) : deliverable.qc_passed ? (
            <span className="deliverable-ok">QC pass</span>
          ) : null}
        </div>
      ) : null}
      {descPath ? (
        <div className="deliverable-row">
          <span>Show description ready at {descPath}</span>
        </div>
      ) : null}
    </footer>
  );
}
