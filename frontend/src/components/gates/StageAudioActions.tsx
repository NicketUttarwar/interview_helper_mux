import { useRef } from "react";
import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";

export function StageAudioActions({ stage }: { stage: StageInfo }) {
  const { runId, showToast } = useApp();
  const inlineRef = useRef<HTMLAudioElement | null>(null);
  const outputs = stage.audio_outputs_present || [];
  if (!outputs.length || !runId) return null;

  const playPath = async (path: string) => {
    const url = `/api/runs/${runId}/audio?path=${encodeURIComponent(path)}`;
    const player = document.querySelector(
      ".audio-player",
    ) as HTMLAudioElement | null;
    const target = player || inlineRef.current;
    if (!target) {
      showToast("Could not play audio — no player available.");
      return;
    }
    target.src = url;
    target.currentTime = 0;
    try {
      await target.play();
    } catch {
      showToast("Could not play audio — check Logs or open the Files tab.");
    }
  };

  return (
    <div className="stage-audio-actions">
      <p className="hint">
        <strong>Listen</strong> stage output audio:
      </p>
      <audio ref={inlineRef} controls className="stage-inline-audio" />
      {outputs.map((path) => (
        <button
          key={path}
          type="button"
          className="btn ghost sm"
          onClick={() => void playPath(path)}
        >
          Listen {path.split("/").pop()}
        </button>
      ))}
    </div>
  );
}
