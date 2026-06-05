import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";
import type { TranscriptState, TranscriptWord } from "../../types";

export interface TranscriptFocusRange {
  start_ms: number;
  end_ms: number;
  label?: string;
}

interface Props {
  /** Optional time range to emphasize (e.g. current review chunk). */
  focusRange?: TranscriptFocusRange | null;
  /** Seek playback to focus range when it changes. */
  seekOnFocus?: boolean;
  compact?: boolean;
}

function findActiveWordIndex(words: TranscriptWord[], timeMs: number): number {
  if (!words.length) return -1;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (timeMs >= w.start_ms && timeMs < w.end_ms) return i;
  }
  if (timeMs >= words[words.length - 1].end_ms) return words.length - 1;
  return -1;
}

export function TranscriptDockViewer({
  focusRange = null,
  seekOnFocus = false,
  compact = false,
}: Props) {
  const { runId, showToast } = useApp();
  const [transcript, setTranscript] = useState<TranscriptState | null>(null);
  const [words, setWords] = useState<TranscriptWord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [followPlayback, setFollowPlayback] = useState(true);

  const playerRef = useRef<HTMLAudioElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wordRefs = useRef<Map<number, HTMLSpanElement>>(new Map());
  const pendingSaves = useRef<Map<number, string>>(new Map());
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFocusKey = useRef<string>("");

  const loadTranscript = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api<TranscriptState>(`/api/runs/${runId}/transcript`);
      setTranscript(data);
      setWords(data.words || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load transcript");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void loadTranscript();
  }, [loadTranscript]);

  const audioUrl = useMemo(() => {
    if (!runId || !transcript?.audio_path) return "";
    return `/api/runs/${runId}/audio?path=${encodeURIComponent(transcript.audio_path)}`;
  }, [runId, transcript?.audio_path]);

  const durationMs = transcript?.duration_ms || 0;
  const lowThreshold = transcript?.low_confidence_threshold ?? 0.85;
  const activeIndex = findActiveWordIndex(words, playheadMs);

  const flushSaves = useCallback(async () => {
    if (!runId || pendingSaves.current.size === 0) return;
    const updates = Array.from(pendingSaves.current.entries()).map(([index, text]) => ({
      index,
      text,
    }));
    pendingSaves.current.clear();
    setSaveStatus("saving");
    try {
      const result = await api<{ words?: TranscriptWord[] }>(
        `/api/runs/${runId}/transcript/words`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ updates }),
        },
      );
      if (result.words) setWords(result.words);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 1800);
    } catch (e) {
      setSaveStatus("idle");
      showToast(e instanceof Error ? e.message : "Save failed");
      for (const u of updates) pendingSaves.current.set(u.index, u.text);
    }
  }, [runId, showToast]);

  const queueSave = useCallback(
    (index: number, text: string) => {
      pendingSaves.current.set(index, text.trim());
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => void flushSaves(), 450);
    },
    [flushSaves],
  );

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      if (pendingSaves.current.size) void flushSaves();
    };
  }, [flushSaves]);

  const seekTo = useCallback((ms: number) => {
    setPlayheadMs(ms);
    if (playerRef.current) playerRef.current.currentTime = ms / 1000;
  }, []);

  useEffect(() => {
    if (!focusRange || !seekOnFocus) return;
    const key = `${focusRange.start_ms}-${focusRange.end_ms}`;
    if (key === lastFocusKey.current) return;
    lastFocusKey.current = key;
    seekTo(focusRange.start_ms);
  }, [focusRange, seekOnFocus, seekTo]);

  useEffect(() => {
    if (!followPlayback || editingIndex !== null || activeIndex < 0) return;
    const el = wordRefs.current.get(activeIndex);
    if (!el || !scrollRef.current) return;
    const container = scrollRef.current;
    const elTop = el.offsetTop;
    const elBottom = elTop + el.offsetHeight;
    const viewTop = container.scrollTop;
    const viewBottom = viewTop + container.clientHeight;
    if (elTop < viewTop + 40 || elBottom > viewBottom - 40) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [activeIndex, followPlayback, editingIndex]);

  const togglePlay = () => {
    const player = playerRef.current;
    if (!player) return;
    if (player.paused) void player.play();
    else player.pause();
  };

  const commitEdit = (index: number) => {
    const trimmed = editDraft.trim();
    if (!trimmed) {
      setEditingIndex(null);
      return;
    }
    setWords((prev) => {
      const next = [...prev];
      if (next[index]) next[index] = { ...next[index], text: trimmed, corrected: true };
      return next;
    });
    queueSave(index, trimmed);
    setEditingIndex(null);
  };

  const startEdit = (index: number) => {
    setEditingIndex(index);
    setEditDraft(words[index]?.text || "");
  };

  const onWordKeyDown = (e: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitEdit(index);
    } else if (e.key === "Escape") {
      setEditingIndex(null);
    }
  };

  const speakerLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const sp of transcript?.speakers || []) {
      map.set(sp.id, sp.role && sp.role !== "unknown" ? sp.role : sp.id);
    }
    return map;
  }, [transcript?.speakers]);

  if (loading) {
    return (
      <div className="transcript-dock transcript-dock-loading">
        <div className="transcript-dock-shimmer" />
        <p className="muted">Loading word-level transcript…</p>
      </div>
    );
  }

  if (error) return <p className="empty-state">{error}</p>;
  if (!transcript?.ready || !words.length) {
    return <p className="empty-state">No transcript yet — run transcribe first.</p>;
  }

  const progressPct = durationMs > 0 ? Math.min(100, (playheadMs / durationMs) * 100) : 0;

  return (
    <div className={`transcript-dock${compact ? " compact" : ""}`}>
      <div className="transcript-dock-toolbar">
        <button
          type="button"
          className="transcript-play-btn"
          onClick={togglePlay}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
              <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M8 5v14l11-7z" fill="currentColor" />
            </svg>
          )}
        </button>
        <div className="transcript-time">
          <span>{formatMs(playheadMs)}</span>
          <span className="muted"> / {formatMs(durationMs)}</span>
        </div>
        <div className="transcript-progress-track">
          <div className="transcript-progress-fill" style={{ width: `${progressPct}%` }} />
          <input
            type="range"
            className="transcript-progress-slider"
            min={0}
            max={durationMs}
            value={playheadMs}
            onChange={(e) => seekTo(Number(e.target.value))}
            aria-label="Seek"
          />
        </div>
        <label className="transcript-follow-toggle">
          <input
            type="checkbox"
            checked={followPlayback}
            onChange={(e) => setFollowPlayback(e.target.checked)}
          />
          Follow
        </label>
        {saveStatus !== "idle" ? (
          <span className={`transcript-save-pill ${saveStatus}`}>
            {saveStatus === "saving" ? "Saving…" : "Saved"}
          </span>
        ) : null}
        {focusRange ? (
          <span className="transcript-focus-badge">
            {focusRange.label || "Review clip"} · {formatMs(focusRange.start_ms)}–
            {formatMs(focusRange.end_ms)}
          </span>
        ) : null}
      </div>

      <audio
        ref={playerRef}
        className="transcript-dock-audio-hidden"
        src={audioUrl}
        preload="metadata"
        onTimeUpdate={() => {
          const t = playerRef.current?.currentTime ?? 0;
          setPlayheadMs(Math.round(t * 1000));
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />

      <div className="transcript-dock-body" ref={scrollRef}>
        <div className="transcript-word-flow">
          {words.map((word, i) => {
            const inFocus =
              !focusRange ||
              (word.start_ms >= focusRange.start_ms - 80 &&
                word.end_ms <= focusRange.end_ms + 80);
            const isActive = i === activeIndex && playing;
            const isSpoken = i < activeIndex || (i === activeIndex && !playing && playheadMs > word.end_ms);
            const isLowConf =
              word.confidence != null && word.confidence < lowThreshold && !word.corrected;
            const showSpeaker =
              word.speaker_id &&
              (i === 0 || words[i - 1]?.speaker_id !== word.speaker_id);

            return (
              <span key={`${i}-${word.start_ms}`} className="transcript-word-wrap">
                {showSpeaker ? (
                  <span className="transcript-speaker-tag">
                    {speakerLabels.get(word.speaker_id!) || word.speaker_id}
                  </span>
                ) : null}
                {editingIndex === i ? (
                  <input
                    className="transcript-word-input"
                    value={editDraft}
                    autoFocus
                    onChange={(e) => setEditDraft(e.target.value)}
                    onBlur={() => commitEdit(i)}
                    onKeyDown={(e) => onWordKeyDown(e, i)}
                  />
                ) : (
                  <span
                    ref={(el) => {
                      if (el) wordRefs.current.set(i, el);
                      else wordRefs.current.delete(i);
                    }}
                    className={[
                      "transcript-word",
                      isActive ? "active" : "",
                      isSpoken ? "spoken" : "",
                      isLowConf ? "low-conf" : "",
                      word.corrected ? "corrected" : "",
                      focusRange && !inFocus ? "out-of-focus" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    role="button"
                    tabIndex={0}
                    title={
                      word.confidence != null
                        ? `${formatMs(word.start_ms)} · ${Math.round(word.confidence * 100)}% confidence`
                        : formatMs(word.start_ms)
                    }
                    onClick={() => seekTo(word.start_ms)}
                    onDoubleClick={() => startEdit(i)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") startEdit(i);
                    }}
                  >
                    {word.text}
                  </span>
                )}
                {" "}
              </span>
            );
          })}
        </div>
      </div>

      <div className="transcript-dock-footer">
        <span className="muted">
          Click a word to seek · double-click to edit · edits save automatically
        </span>
        <span className="muted">{words.length} words</span>
      </div>
    </div>
  );
}
