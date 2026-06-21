import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";
import {
  FUZZY_MATCH_DEFAULT,
  findFuzzyWordMatches,
} from "../../utils/fuzzyMatch";
import type { TranscriptState, TranscriptWord } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import {
  addCorrectionStats,
  emptyCorrectionStats,
  formatCorrectionSummary,
  type TranscriptCorrectionStats,
} from "../../utils/transcriptCorrectionStats";
import { FuzzyReplacePopover } from "./FuzzyReplacePopover";

export type { TranscriptCorrectionStats };
export { formatCorrectionSummary };

export interface TranscriptFocusRange {
  start_ms: number;
  end_ms: number;
  label?: string;
}

interface WordUndoSnapshot {
  index: number;
  text: string;
  corrected?: boolean;
}

interface UndoEntry {
  snapshots: WordUndoSnapshot[];
  statsDelta: TranscriptCorrectionStats;
}

interface Props {
  /** Optional time range to emphasize (e.g. current review chunk). */
  focusRange?: TranscriptFocusRange | null;
  /** Seek playback to focus range when it changes. */
  seekOnFocus?: boolean;
  compact?: boolean;
  /** Called after word edits persist (e.g. refresh chunk textarea). */
  onWordsSaved?: () => void;
  /** Session correction totals for review summary. */
  onCorrectionStatsChange?: (stats: TranscriptCorrectionStats) => void;
}

const BATCH_REPLACE_CONFIRM_MIN = 3;
const MAX_UNDO_STACK = 30;

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
  onWordsSaved,
  onCorrectionStatsChange,
}: Props) {
  const { runId, showToast, appendClientLog, confirm } = useApp();
  const [transcript, setTranscript] = useState<TranscriptState | null>(null);
  const [words, setWords] = useState<TranscriptWord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [editOriginalText, setEditOriginalText] = useState("");
  const [fuzzyMinScore, setFuzzyMinScore] = useState(FUZZY_MATCH_DEFAULT);
  const [selectedFuzzyIndices, setSelectedFuzzyIndices] = useState<Set<number>>(new Set());
  const [fuzzyPopoverDismissed, setFuzzyPopoverDismissed] = useState(false);
  const [correctionStats, setCorrectionStats] = useState<TranscriptCorrectionStats>(
    emptyCorrectionStats,
  );
  const [editAnchorEl, setEditAnchorEl] = useState<HTMLElement | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [followPlayback, setFollowPlayback] = useState(true);
  const [undoAvailable, setUndoAvailable] = useState(false);

  const playerRef = useRef<HTMLAudioElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wordRefs = useRef<Map<number, HTMLSpanElement>>(new Map());
  const editInputRef = useRef<HTMLInputElement>(null);
  const pendingSaves = useRef<Map<number, string>>(new Map());
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFocusKey = useRef<string>("");
  const prevFuzzyMatchCount = useRef(0);
  const undoStack = useRef<UndoEntry[]>([]);
  const dockRef = useRef<HTMLDivElement>(null);

  const loadTranscript = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api<TranscriptState>(`/api/runs/${runId}/transcript`);
      setTranscript(data);
      setWords(data.words || []);
    } catch (reason) {
      const msg = formatApiError(reason, "Transcript");
      setError(msg);
      appendClientLog(msg, "error");
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
      onWordsSaved?.();
    } catch (reason) {
      setSaveStatus("idle");
      const msg = formatApiError(reason, "Save transcript words");
      showToast(msg, "error");
      appendClientLog(msg, "error");
      for (const u of updates) pendingSaves.current.set(u.index, u.text);
    }
  }, [runId, showToast, appendClientLog, onWordsSaved]);

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

  const seekToWord = useCallback(
    (index: number) => {
      const word = words[index];
      if (!word) return;
      seekTo(word.start_ms);
      wordRefs.current.get(index)?.scrollIntoView({ block: "center", behavior: "smooth" });
    },
    [words, seekTo],
  );

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

  const fuzzyMatches = useMemo(() => {
    if (editingIndex === null) return [];
    return findFuzzyWordMatches(
      words,
      editingIndex,
      editOriginalText,
      fuzzyMinScore,
      editDraft,
    );
  }, [words, editingIndex, editOriginalText, fuzzyMinScore, editDraft]);

  const approvedFuzzyMatches = useMemo(
    () => fuzzyMatches.filter((m) => selectedFuzzyIndices.has(m.index)),
    [fuzzyMatches, selectedFuzzyIndices],
  );

  const fuzzyCandidateIndices = useMemo(() => {
    if (editingIndex === null || fuzzyPopoverDismissed) return new Set<number>();
    return new Set(approvedFuzzyMatches.map((m) => m.index));
  }, [editingIndex, fuzzyPopoverDismissed, approvedFuzzyMatches]);

  const recordCorrection = useCallback(
    (totalAdded: number, fuzzyBatchAdded: number) => {
      if (totalAdded <= 0) return;
      setCorrectionStats((prev) => {
        const next = addCorrectionStats(prev, totalAdded, fuzzyBatchAdded);
        onCorrectionStatsChange?.(next);
        return next;
      });
    },
    [onCorrectionStatsChange],
  );

  const pushUndo = useCallback(
    (indices: number[], statsDelta: TranscriptCorrectionStats) => {
      const snap: WordUndoSnapshot[] = [];
      for (const index of indices) {
        const word = words[index];
        if (!word) continue;
        snap.push({ index, text: word.text, corrected: word.corrected });
      }
      if (!snap.length) return;
      undoStack.current.push({ snapshots: snap, statsDelta });
      if (undoStack.current.length > MAX_UNDO_STACK) undoStack.current.shift();
      setUndoAvailable(true);
    },
    [words],
  );

  const endEdit = () => {
    setEditingIndex(null);
    setFuzzyPopoverDismissed(false);
    setSelectedFuzzyIndices(new Set());
  };

  const applyWordUpdates = useCallback(
    (indices: number[], text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setWords((prev) => {
        const next = [...prev];
        for (const idx of indices) {
          if (next[idx]) next[idx] = { ...next[idx], text: trimmed, corrected: true };
        }
        return next;
      });
      for (const idx of indices) queueSave(idx, trimmed);
    },
    [queueSave],
  );

  const commitEdit = (index: number) => {
    const trimmed = editDraft.trim();
    if (!trimmed) {
      endEdit();
      return;
    }
    if (words[index]?.text !== trimmed) {
      pushUndo([index], { total: 1, fuzzyBatch: 0 });
      recordCorrection(1, 0);
    }
    applyWordUpdates([index], trimmed);
    endEdit();
  };

  const applyFuzzyReplace = async () => {
    if (editingIndex === null) return;
    const trimmed = editDraft.trim();
    if (!trimmed) return;

    const targetIndices = new Set<number>([editingIndex]);
    for (const m of approvedFuzzyMatches) targetIndices.add(m.index);
    const indices = Array.from(targetIndices);
    const fuzzyBatchCount = approvedFuzzyMatches.length;

    if (indices.length >= BATCH_REPLACE_CONFIRM_MIN) {
      const ok = await confirm(
        fuzzyBatchCount > 0
          ? `Replace ${indices.length} words with “${trimmed}”? ${fuzzyBatchCount} similar match${fuzzyBatchCount === 1 ? "" : "es"} plus the word you are editing.`
          : `Replace this word with “${trimmed}”?`,
      );
      if (!ok) return;
    }

    const changed = indices.filter((idx) => words[idx]?.text !== trimmed);
    const fuzzyChangedCount = changed.filter((idx) =>
      approvedFuzzyMatches.some((m) => m.index === idx),
    ).length;
    if (changed.length) {
      pushUndo(changed, { total: changed.length, fuzzyBatch: fuzzyChangedCount });
      recordCorrection(changed.length, fuzzyChangedCount);
    }
    applyWordUpdates(indices, trimmed);
    const summary = formatCorrectionSummary({
      total: changed.length,
      fuzzyBatch: fuzzyChangedCount,
    });
    showToast(summary || `Updated ${indices.length} words`);
    endEdit();
  };

  const undoLastEdit = useCallback(async () => {
    const entry = undoStack.current.pop();
    if (!entry?.snapshots.length) {
      setUndoAvailable(undoStack.current.length > 0);
      return;
    }
    setUndoAvailable(undoStack.current.length > 0);
    setWords((prev) => {
      const next = [...prev];
      for (const s of entry.snapshots) {
        if (!next[s.index]) continue;
        next[s.index] = {
          ...next[s.index],
          text: s.text,
          corrected: s.corrected,
        };
      }
      return next;
    });
    setCorrectionStats((prev) => {
      const next = {
        total: Math.max(0, prev.total - entry.statsDelta.total),
        fuzzyBatch: Math.max(0, prev.fuzzyBatch - entry.statsDelta.fuzzyBatch),
      };
      onCorrectionStatsChange?.(next);
      return next;
    });
    if (saveTimer.current) clearTimeout(saveTimer.current);
    for (const s of entry.snapshots) pendingSaves.current.set(s.index, s.text);
    await flushSaves();
    showToast("Undid last edit");
  }, [flushSaves, showToast, onCorrectionStatsChange]);

  const handleEditBlur = (index: number) => {
    window.setTimeout(() => {
      const active = document.activeElement;
      if (active?.closest(".fuzzy-replace-popover")) return;
      commitEdit(index);
    }, 0);
  };

  const startEdit = (index: number) => {
    const original = words[index]?.text || "";
    setEditingIndex(index);
    setEditDraft(original);
    setEditOriginalText(original);
    setFuzzyMinScore(FUZZY_MATCH_DEFAULT);
    setSelectedFuzzyIndices(new Set());
    setFuzzyPopoverDismissed(false);
  };

  const onWordKeyDown = (e: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitEdit(index);
    } else if (e.key === "Escape") {
      endEdit();
    }
  };

  const showFuzzyPopover = editingIndex !== null && !fuzzyPopoverDismissed;

  useLayoutEffect(() => {
    if (editingIndex === null) {
      setEditAnchorEl(null);
      return;
    }
    setEditAnchorEl(editInputRef.current);
  }, [editingIndex, editDraft]);

  useEffect(() => {
    if (editingIndex === null) {
      prevFuzzyMatchCount.current = 0;
      return;
    }
    setSelectedFuzzyIndices((prev) => {
      const next = new Set(prev);
      const matchIndices = new Set(fuzzyMatches.map((m) => m.index));
      for (const m of fuzzyMatches) next.add(m.index);
      for (const idx of next) {
        if (!matchIndices.has(idx)) next.delete(idx);
      }
      return next;
    });
    prevFuzzyMatchCount.current = fuzzyMatches.length;
  }, [fuzzyMatches, editingIndex]);

  useEffect(() => {
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (editingIndex !== null) return;
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      if (!undoStack.current.length) return;
      e.preventDefault();
      void undoLastEdit();
    };
    const el = dockRef.current;
    el?.addEventListener("keydown", onKeyDown);
    return () => el?.removeEventListener("keydown", onKeyDown);
  }, [editingIndex, undoLastEdit]);

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
    <div
      ref={dockRef}
      className={`transcript-dock${compact ? " compact" : ""}`}
      tabIndex={-1}
    >
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
        {undoAvailable ? (
          <button
            type="button"
            className="btn sm ghost transcript-undo-btn"
            onClick={() => void undoLastEdit()}
          >
            Undo
          </button>
        ) : null}
        {correctionStats.total > 0 ? (
          <span className="transcript-correction-summary-pill" title="Session correction total">
            {formatCorrectionSummary(correctionStats)}
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
                  <span className="transcript-word-edit-wrap">
                    <input
                      ref={editInputRef}
                      className="transcript-word-input"
                      value={editDraft}
                      autoFocus
                      onChange={(e) => setEditDraft(e.target.value)}
                      onBlur={() => handleEditBlur(i)}
                      onKeyDown={(e) => onWordKeyDown(e, i)}
                    />
                    {fuzzyPopoverDismissed ? (
                      <button
                        type="button"
                        className="fuzzy-reopen-btn"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => setFuzzyPopoverDismissed(false)}
                      >
                        Find similar
                      </button>
                    ) : null}
                  </span>
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
                      fuzzyCandidateIndices.has(i) ? "fuzzy-candidate" : "",
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
          Click to seek · double-click to edit · ⌘Z undo · similar-word fixer while editing
        </span>
        <span className="muted">{words.length} words</span>
      </div>

      {showFuzzyPopover ? (
        <FuzzyReplacePopover
          anchorEl={editAnchorEl}
          sourceText={editOriginalText}
          correctionDraft={editDraft}
          matches={fuzzyMatches}
          selectedMatchIndices={selectedFuzzyIndices}
          minScore={fuzzyMinScore}
          onMinScoreChange={setFuzzyMinScore}
          onToggleMatch={(index, included) => {
            setSelectedFuzzyIndices((prev) => {
              const next = new Set(prev);
              if (included) next.add(index);
              else next.delete(index);
              return next;
            });
          }}
          onSelectAllMatches={() => {
            setSelectedFuzzyIndices(new Set(fuzzyMatches.map((m) => m.index)));
          }}
          onClearAllMatches={() => setSelectedFuzzyIndices(new Set())}
          onReplace={() => void applyFuzzyReplace()}
          onClose={() => setFuzzyPopoverDismissed(true)}
          onSeekToMatch={seekToWord}
        />
      ) : null}
    </div>
  );
}
