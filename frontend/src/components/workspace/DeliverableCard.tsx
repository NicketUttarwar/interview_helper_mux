import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { useJourney } from "../../hooks/useJourney";
import { ActionMarker } from "../guidance/ActionMarker";

export function DeliverableCard() {
  const { run, runId, refreshRun, config, setActiveTab, setPipelineSubTab, setActivityLogTab } =
    useApp();
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

  const openActivity = () => {
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    setActivityLogTab("live");
  };

  return (
    <footer id="workflow-deliverable" className="deliverable-card panel">
      <h4>Export phase</h4>
      <p className="hint phase-guidance-goal">
        {run.journey?.phase_guidance?.ship?.goal ||
          "Download your master WAV or show description from the run folder."}
      </p>
      <p className="hint sm">
        Files live under your run directory — copy paths below or open them in Finder from the
        execution folder on disk.
      </p>
      {previewPath && phase !== "ship" ? (
        <div className="deliverable-row">
          <ActionMarker status="todo" />
          <span>Listen to assembly preview before sound spend</span>
          <audio controls src={playUrl(previewPath)} />
          <button type="button" className="btn ghost sm" onClick={() => void onPreviewListened()}>
            Continue to sound
          </button>
          <button type="button" className="btn ghost sm" onClick={openActivity}>
            View activity
          </button>
        </div>
      ) : null}
      {masterPath ? (
        <div className="deliverable-row">
          <span>Master</span>
          <code className="deliverable-path">{masterPath}</code>
          <audio controls src={playUrl(masterPath)} />
          {deliverable.qc_passed === false ? (
            <span className="deliverable-warn">QC check failed — see activity log</span>
          ) : deliverable.qc_passed ? (
            <span className="deliverable-ok">QC pass</span>
          ) : null}
        </div>
      ) : null}
      {descPath ? (
        <div className="deliverable-row">
          <span>Show description</span>
          <code className="deliverable-path">{descPath}</code>
        </div>
      ) : null}
    </footer>
  );
}
