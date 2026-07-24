import { useEffect, useRef } from "react";
import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { loadAndPlay, registerExclusiveAudio } from "../../utils/audioPlayback";

export function StageAudioActions({ stage }: { stage: StageInfo }) {
  const { runId, showToast } = useApp();
  const inlineRef = useRef<HTMLAudioElement | null>(null);
  const outputs = stage.audio_outputs_present || [];

  useEffect(() => {
    const el = inlineRef.current;
    if (!el) return;
    return registerExclusiveAudio(el);
  }, []);

  if (!outputs.length || !runId) return null;

  const playPath = async (path: string) => {
    const url = `/api/runs/${runId}/audio?path=${encodeURIComponent(path)}`;
    const target = inlineRef.current;
    if (!target) {
      showToast("Could not play audio — no player available.");
      return;
    }
    try {
      await loadAndPlay(target, url);
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
