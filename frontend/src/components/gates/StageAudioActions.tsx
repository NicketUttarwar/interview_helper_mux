import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";

export function StageAudioActions({ stage }: { stage: StageInfo }) {
  const { runId } = useApp();
  const outputs = stage.audio_outputs_present || [];
  if (!outputs.length || !runId) return null;

  return (
    <div className="stage-audio-actions">
      <p className="hint">
        <strong>Listen</strong> stage output audio:
      </p>
      {outputs.map((path) => (
        <button
          key={path}
          type="button"
          className="btn ghost sm"
          onClick={() => {
            const player = document.querySelector(
              ".audio-player",
            ) as HTMLAudioElement | null;
            if (!player) return;
            const url = `/api/runs/${runId}/audio?path=${encodeURIComponent(path)}`;
            player.src = url;
            player.currentTime = 0;
            void player.play().catch(() => {});
          }}
        >
          Listen {path.split("/").pop()}
        </button>
      ))}
    </div>
  );
}
