import { useMemo } from "react";
import { formatMs } from "../../../utils";
import type { TranscriptFocusRange, TranscriptWord } from "../../../types";

interface Props {
  words: TranscriptWord[];
  playheadMs: number;
  focusRange?: TranscriptFocusRange | null;
  onSeek: (ms: number) => void;
  onWordRangeSelect?: (startMs: number, endMs: number) => void;
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
  onSeek,
  onWordRangeSelect,
}: Props) {
  const activeIndex = findActiveWordIndex(words, playheadMs);

  const visibleWords = useMemo(() => {
    if (!focusRange) return words;
    return words.filter(
      (w) =>
        w.start_ms >= focusRange.start_ms - 80 && w.end_ms <= focusRange.end_ms + 80,
    );
  }, [words, focusRange]);

  if (!words.length) {
    return <p className="muted transcript-strip-empty">Transcript unavailable — run transcribe first.</p>;
  }

  return (
    <div className="transcript-strip">
      <div className="transcript-strip-toolbar">
        <span className="muted">
          {focusRange
            ? `Segment words · ${formatMs(focusRange.start_ms)}–${formatMs(focusRange.end_ms)}`
            : "Click word to seek · double-click range endpoints to trim"}
        </span>
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
      <div className="transcript-strip-body">
        {visibleWords.map((word) => {
          const globalIdx = words.indexOf(word);
          const isActive = globalIdx === activeIndex;
          const inFocus =
            !focusRange ||
            (word.start_ms >= focusRange.start_ms && word.end_ms <= focusRange.end_ms);
          return (
            <span
              key={`${globalIdx}-${word.start_ms}`}
              className={[
                "transcript-word",
                isActive ? "active" : "",
                focusRange && !inFocus ? "out-of-focus" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              role="button"
              tabIndex={0}
              title={formatMs(word.start_ms)}
              onClick={() => onSeek(word.start_ms)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSeek(word.start_ms);
              }}
            >
              {word.text}
            </span>
          );
        })}
      </div>
    </div>
  );
}
