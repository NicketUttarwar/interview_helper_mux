import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { usePreviewListenGate } from "../../hooks/usePreviewListenGate";
import { useAsyncAction } from "../../hooks/useAsyncAction";
import { ArtifactAudio } from "../shared/ArtifactAudio";

interface Props {
  compact?: boolean;
}

export function PreviewListenPromo({ compact }: Props) {
  const { run, runId, refreshRun, config, setActiveTab, setPipelineSubTab, showToast } = useApp();
  const { busy, run: runListen } = useAsyncAction("preview-listen");
  const requirePreview = config?.journey_ui?.require_preview_listen !== false;
  const { active, previewPath } = usePreviewListenGate(run, requirePreview);

  if (!active || !previewPath || !runId) return null;

  const playUrl = `/api/runs/${runId}/audio?path=${encodeURIComponent(previewPath)}`;

  const onListened = () =>
    void runListen(
      async () => {
        await api(`/api/runs/${runId}/milestones/preview-listened`, { method: "POST" });
        await refreshRun();
      },
      {
        showToast,
        startMessage: "Recording preview listen milestone…",
        successMessage: "Preview listened — you can continue to sound design.",
      },
    );

  const openPipeline = () => {
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
  };

  return (
    <div
      className={`preview-listen-promo panel-inset${compact ? " compact" : ""}`}
      id="preview-listen-promo"
      role="region"
      aria-label="Assembly preview listen gate"
    >
      <div className="preview-listen-copy">
        <p className="preview-listen-title">Listen to preview before sound spend</p>
        {!compact ? (
          <p className="hint sm">
            Play the speech + VO assembly preview. Continue only when the edit order sounds right.
          </p>
        ) : null}
      </div>
      <ArtifactAudio
        src={playUrl}
        className={`preview-listen-audio${compact ? " preview-listen-audio--compact" : ""}`}
      />
      <div className="preview-listen-actions">
        {compact ? (
          <button type="button" className="btn ghost sm" onClick={openPipeline}>
            Open preview
          </button>
        ) : null}
        <button
          type="button"
          className="btn primary sm"
          disabled={busy}
          onClick={onListened}
        >
          {busy ? (
            <>
              <span className="spinner-inline" aria-hidden /> Saving…
            </>
          ) : (
            "I've listened — continue to sound"
          )}
        </button>
      </div>
    </div>
  );
}
