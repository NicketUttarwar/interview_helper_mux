import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { usePreviewListenGate } from "../../hooks/usePreviewListenGate";

interface Props {
  compact?: boolean;
}

export function PreviewListenPromo({ compact }: Props) {
  const { run, runId, refreshRun, config, setActiveTab, setPipelineSubTab } = useApp();
  const requirePreview = config?.journey_ui?.require_preview_listen !== false;
  const { active, previewPath } = usePreviewListenGate(run, requirePreview);

  if (!active || !previewPath || !runId) return null;

  const playUrl = `/api/runs/${runId}/audio?path=${encodeURIComponent(previewPath)}`;

  const onListened = async () => {
    await api(`/api/runs/${runId}/milestones/preview-listened`, { method: "POST" });
    await refreshRun();
  };

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
      {!compact ? <audio controls src={playUrl} className="preview-listen-audio" /> : null}
      <div className="preview-listen-actions">
        {compact ? (
          <button type="button" className="btn ghost sm" onClick={openPipeline}>
            Open preview
          </button>
        ) : null}
        <button type="button" className="btn primary sm" onClick={() => void onListened()}>
          I&apos;ve listened — continue to sound
        </button>
      </div>
    </div>
  );
}
