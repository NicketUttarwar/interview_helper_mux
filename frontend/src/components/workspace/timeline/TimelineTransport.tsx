import { useEffect } from "react";
import { formatMs } from "../../../utils";

interface Props {
  playheadMs: number;
  durationMs: number;
  playing: boolean;
  playbackSpeed: number;
  loopSelection: boolean;
  followPlayback: boolean;
  hasSelection: boolean;
  onTogglePlay: () => void;
  onSeek: (ms: number) => void;
  onSpeedChange: (speed: number) => void;
  onLoopChange: (loop: boolean) => void;
  onFollowChange: (follow: boolean) => void;
  playerRef: React.RefObject<HTMLAudioElement | null>;
  loopStartMs?: number;
  loopEndMs?: number;
}

const SPEEDS = [1, 1.25, 1.5, 2];

export function TimelineTransport({
  playheadMs,
  durationMs,
  playing,
  playbackSpeed,
  loopSelection,
  followPlayback,
  hasSelection,
  onTogglePlay,
  onSeek,
  onSpeedChange,
  onLoopChange,
  onFollowChange,
  playerRef,
  loopStartMs,
  loopEndMs,
}: Props) {
  const progressPct = durationMs > 0 ? Math.min(100, (playheadMs / durationMs) * 100) : 0;

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !loopSelection || loopStartMs == null || loopEndMs == null) return;
    const onTime = () => {
      const t = player.currentTime * 1000;
      if (t >= loopEndMs) {
        player.currentTime = loopStartMs / 1000;
      }
    };
    player.addEventListener("timeupdate", onTime);
    return () => player.removeEventListener("timeupdate", onTime);
  }, [playerRef, loopSelection, loopStartMs, loopEndMs]);

  return (
    <div className="timeline-transport">
      <button
        type="button"
        className="transcript-play-btn"
        onClick={onTogglePlay}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <span className="timeline-transport-time">
        {formatMs(playheadMs)} <span className="muted">/ {formatMs(durationMs)}</span>
      </span>
      <div className="transcript-progress-track timeline-transport-track">
        <div className="transcript-progress-fill" style={{ width: `${progressPct}%` }} />
        <input
          type="range"
          className="transcript-progress-slider"
          min={0}
          max={durationMs}
          value={playheadMs}
          onChange={(e) => onSeek(Number(e.target.value))}
          aria-label="Seek"
        />
      </div>
      <label className="timeline-transport-speed">
        Speed{" "}
        <select
          value={playbackSpeed}
          onChange={(e) => onSpeedChange(Number(e.target.value))}
        >
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>
      <label className="timeline-transport-toggle">
        <input
          type="checkbox"
          checked={loopSelection}
          disabled={!hasSelection}
          onChange={(e) => onLoopChange(e.target.checked)}
        />
        Loop selection
      </label>
      <label className="timeline-transport-toggle">
        <input
          type="checkbox"
          checked={followPlayback}
          onChange={(e) => onFollowChange(e.target.checked)}
        />
        Follow
      </label>
    </div>
  );
}
