import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { useJourney } from "../../hooks/useJourney";
import { usePreviewListenGate } from "../../hooks/usePreviewListenGate";
import { useAsyncAction } from "../../hooks/useAsyncAction";

export function DeliverableCard() {
  const { run, runId, refreshRun, config, setActiveTab, setPipelineSubTab, setActivityLogTab, setLogFilterPreset, showToast } =
    useApp();
  const { deliverable, phase } = useJourney(run);
  const enabled = config?.journey_ui?.enabled !== false;
  const requirePreview = config?.journey_ui?.require_preview_listen !== false;
  const { active: previewPromoActive } = usePreviewListenGate(run, requirePreview);
  const { busy: previewBusy, run: runPreviewAction } = useAsyncAction("preview listened");

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
    await runPreviewAction(
      async () => {
        await api(`/api/runs/${runId}/milestones/preview-listened`, { method: "POST" });
        await refreshRun();
      },
      {
        showToast,
        startMessage: "Recording preview listen…",
        successMessage: "Preview listen recorded — continue to sound design",
        errorMessage: "Preview listened",
      },
    );
  };

  const openActivity = () => {
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    setActivityLogTab("live");
  };

  const openActivityErrors = () => {
    setLogFilterPreset({ level: "error", stream: "all", scrollToError: true });
    setActiveTab("logs");
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
      {previewPath && phase !== "ship" && !previewPromoActive ? (
        <div className="deliverable-row">
          <span>Listen to assembly preview before sound spend</span>
          <audio controls src={playUrl(previewPath)} />
          <button
            type="button"
            className="btn ghost sm"
            disabled={previewBusy}
            onClick={() => void onPreviewListened()}
          >
            {previewBusy ? (
              <>
                <span className="spinner-inline" aria-hidden /> Saving…
              </>
            ) : (
              "Continue to sound"
            )}
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
            <>
              <span className="deliverable-warn">QC check failed — see activity log</span>
              <button type="button" className="btn ghost sm" onClick={openActivityErrors}>
                View errors
              </button>
            </>
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
