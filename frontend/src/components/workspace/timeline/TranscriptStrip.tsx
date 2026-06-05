import { useEffect, useMemo, useRef, useState } from "react";
import { formatMs } from "../../../utils";
import type { TimelineSegment, TranscriptFocusRange, TranscriptWord } from "../../../types";

interface Props {
  words: TranscriptWord[];
  playheadMs: number;
  focusRange?: TranscriptFocusRange | null;
  segments?: TimelineSegment[];
  lowThreshold?: number;
  followPlayback?: boolean;
  onSeek: (ms: number) => void;
  onWordRangeSelect?: (startMs: number, endMs: number) => void;
  onExcludeSegment?: () => void;
  onMarkRedo?: () => void;
  onSearchJump?: (segId: string, startMs: number) => void;
}

function findActiveWordIndex(words: TranscriptWord[], timeMs: number): number {
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (timeMs >= w.start_ms && timeMs < w.end_ms) return i;
  }
  return -1;
}

export function TranscriptStrip({
  words,
  playheadMs,
  focusRange,
  segments = [],
  lowThreshold = 0.85,
  followPlayback = true,
  onSeek,
  onWordRangeSelect,
  onExcludeSegment,
  onMarkRedo,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const wordRefs = useRef<Map<number, HTMLSpanElement>>(new Map());
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQ, setSearchQ] = useState("");
  const [searchIdx, setSearchIdx] = useState(0);

  const activeIndex = findActiveWordIndex(words, playheadMs);

  const visibleWords = useMemo(() => {
    if (!focusRange) return words;
    return words.filter(
      (w) =>
        w.start_ms >= focusRange.start_ms - 80 && w.end_ms <= focusRange.end_ms + 80,
    );
  }, [words, focusRange]);

  const searchMatches = useMemo(() => {
    const q = searchQ.trim().toLowerCase();
    if (!q) return [];
    return words
      .map((w, i) => ({ w, i }))
      .filter(({ w }) => w.text.toLowerCase().includes(q));
  }, [words, searchQ]);

  const excludedRanges = useMemo(() => {
    return segments.filter((s) => s._excluded).map((s) => ({ start: s.start_ms, end: s.end_ms }));
  }, [segments]);

  useEffect(() => {
    if (!followPlayback || activeIndex < 0) return;
    const el = wordRefs.current.get(activeIndex);
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex, followPlayback]);

  const handleMouseUp = () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !scrollRef.current) return;
    const anchor = sel.anchorNode?.parentElement;
    const focus = sel.focusNode?.parentElement;
    const aIdx = Number(anchor?.getAttribute("data-word-idx"));
    const fIdx = Number(focus?.getAttribute("data-word-idx"));
    if (!Number.isNaN(aIdx) && !Number.isNaN(fIdx)) {
      const lo = Math.min(aIdx, fIdx);
      const hi = Math.max(aIdx, fIdx);
      setSelection({ start: lo, end: hi });
    }
  };

  const selectionRange =
    selection && words[selection.start] && words[selection.end]
      ? {
          start_ms: words[selection.start].start_ms,
          end_ms: words[selection.end].end_ms,
        }
      : null;

  if (!words.length) {
    return <p className="muted transcript-strip-empty">Transcript unavailable — run transcribe first.</p>;
  }

  return (
    <div className="transcript-strip">
      <div className="transcript-strip-toolbar">
        <span className="muted">
          {focusRange
            ? `Segment words · ${formatMs(focusRange.start_ms)}–${formatMs(focusRange.end_ms)}`
            : "Select words to trim · click to seek"}
        </span>
        <button type="button" className="btn sm ghost" onClick={() => setSearchOpen((o) => !o)}>
          Search
        </button>
        {onWordRangeSelect && focusRange ? (
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => onWordRangeSelect(focusRange.start_ms, focusRange.end_ms)}
          >
            Trim to focus range
          </button>
        ) : null}
      </div>

      {searchOpen ? (
        <div className="transcript-search-panel">
          <input
            type="search"
            value={searchQ}
            placeholder="Find in transcript…"
            onChange={(e) => {
              setSearchQ(e.target.value);
              setSearchIdx(0);
            }}
          />
          <button
            type="button"
            className="btn sm ghost"
            disabled={!searchMatches.length}
            onClick={() => {
              const m = searchMatches[searchIdx % searchMatches.length];
              if (m) onSeek(m.w.start_ms);
              setSearchIdx((i) => i + 1);
            }}
          >
            Find next ({searchMatches.length || 0})
          </button>
          <button
            type="button"
            className="btn sm ghost"
            disabled={!searchMatches.length}
            onClick={() => {
              const m = searchMatches[(searchIdx - 1 + searchMatches.length) % searchMatches.length];
              if (m) onSeek(m.w.start_ms);
              setSearchIdx((i) => Math.max(0, i - 1));
            }}
          >
            Find previous
          </button>
        </div>
      ) : null}

      {selectionRange && onWordRangeSelect ? (
        <div className="transcript-selection-bar">
          <span>
            {formatMs(selectionRange.start_ms)} – {formatMs(selectionRange.end_ms)}
          </span>
          <button
            type="button"
            className="btn sm primary"
            onClick={() => {
              onWordRangeSelect(selectionRange.start_ms, selectionRange.end_ms);
              setSelection(null);
            }}
          >
            Trim to selection
          </button>
          {onExcludeSegment ? (
            <button type="button" className="btn sm ghost" onClick={() => void onExcludeSegment()}>
              Exclude segment
            </button>
          ) : null}
          {onMarkRedo ? (
            <button type="button" className="btn sm ghost" onClick={() => void onMarkRedo()}>
              Mark redo
            </button>
          ) : null}
          <button type="button" className="btn sm ghost" onClick={() => setSelection(null)}>
            Clear
          </button>
        </div>
      ) : null}

      <div
        className="transcript-strip-body"
        ref={scrollRef}
        onMouseUp={handleMouseUp}
      >
        {visibleWords.map((word) => {
          const globalIdx = words.indexOf(word);
          const isActive = globalIdx === activeIndex;
          const inFocus =
            !focusRange ||
            (word.start_ms >= focusRange.start_ms && word.end_ms <= focusRange.end_ms);
          const isLowConf =
            word.confidence != null && word.confidence < lowThreshold && !word.corrected;
          const isExcluded = excludedRanges.some(
            (r) => word.start_ms >= r.start && word.end_ms <= r.end,
          );
          const isSearchHit =
            searchQ &&
            word.text.toLowerCase().includes(searchQ.trim().toLowerCase());
          const inSel =
            selection &&
            globalIdx >= selection.start &&
            globalIdx <= selection.end;
          return (
            <span
              key={`${globalIdx}-${word.start_ms}`}
              ref={(el) => {
                if (el) wordRefs.current.set(globalIdx, el);
              }}
              data-word-idx={globalIdx}
              className={[
                "transcript-word",
                isActive ? "active" : "",
                focusRange && !inFocus ? "out-of-focus" : "",
                isLowConf ? "low-confidence" : "",
                isExcluded ? "excluded-word" : "",
                isSearchHit ? "search-hit" : "",
                inSel ? "text-selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              role="button"
              tabIndex={0}
              title={formatMs(word.start_ms)}
              onClick={() => onSeek(word.start_ms)}
            >
              {word.text}
            </span>
          );
        })}
      </div>
    </div>
  );
}
