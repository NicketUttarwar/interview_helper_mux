import { useLayoutEffect, useState } from "react";
import { formatMs } from "../../utils";
import {
  correctionDiffersFromSource,
  FUZZY_MATCH_FLOOR,
  type FuzzyMatch,
} from "../../utils/fuzzyMatch";

interface Props {
  anchorEl: HTMLElement | null;
  sourceText: string;
  correctionDraft: string;
  matches: FuzzyMatch[];
  selectedMatchIndices: Set<number>;
  minScore: number;
  onMinScoreChange: (score: number) => void;
  onToggleMatch: (index: number, included: boolean) => void;
  onSelectAllMatches: () => void;
  onClearAllMatches: () => void;
  onReplace: () => void;
  onClose: () => void;
  onSeekToMatch: (index: number) => void;
}

const POPOVER_WIDTH = 300;
const POPOVER_GAP = 10;

function computePosition(anchorEl: HTMLElement | null): { left: number; top: number } | null {
  if (!anchorEl) return null;
  const rect = anchorEl.getBoundingClientRect();
  let left = rect.right + POPOVER_GAP;
  let top = rect.top - 4;

  if (left + POPOVER_WIDTH > window.innerWidth - 12) {
    left = Math.max(12, rect.left - POPOVER_WIDTH - POPOVER_GAP);
  }
  top = Math.max(12, Math.min(top, window.innerHeight - 400));

  return { left, top };
}

function scoreClass(score: number): string {
  if (score >= 95) return "high";
  if (score >= 88) return "mid";
  return "low";
}

export function FuzzyReplacePopover({
  anchorEl,
  sourceText,
  correctionDraft,
  matches,
  selectedMatchIndices,
  minScore,
  onMinScoreChange,
  onToggleMatch,
  onSelectAllMatches,
  onClearAllMatches,
  onReplace,
  onClose,
  onSeekToMatch,
}: Props) {
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    setPosition(computePosition(anchorEl));
  }, [anchorEl, matches.length, minScore, selectedMatchIndices.size]);

  const selectedCount = matches.filter((m) => selectedMatchIndices.has(m.index)).length;
  const replaceTotal = selectedCount + 1;
  const trimmedCorrection = correctionDraft.trim();
  const trimmedSource = sourceText.trim();
  const hasCorrection = trimmedCorrection.length > 0;
  const correctionChanged = correctionDiffersFromSource(trimmedSource, trimmedCorrection);
  const canReplace = hasCorrection && correctionChanged;

  const replaceLabel = !canReplace
    ? "Replace"
    : selectedCount > 0
      ? `Replace ${replaceTotal} words`
      : "Replace this word only";

  let hint = "Type your correction above to search the transcript.";
  if (!correctionChanged && hasCorrection) {
    hint = "Change the word to something different to enable replace.";
  } else if (correctionChanged && matches.length === 0) {
    hint = `No other words match “${trimmedSource}” at ${minScore}% or higher.`;
  } else if (correctionChanged && matches.length > 0) {
    hint =
      selectedCount > 0
        ? "Uncheck any close match you want to keep unchanged."
        : "Select similar words below, or replace this word only.";
  }

  if (!position) return null;

  return (
    <>
      <div
        className="segment-context-backdrop fuzzy-replace-backdrop"
        onMouseDown={(e) => {
          e.preventDefault();
          onClose();
        }}
      />
      <div
        className="fuzzy-replace-popover"
        style={{ left: position.left, top: position.top }}
        role="dialog"
        aria-label="Fix similar words"
        onMouseDown={(e) => e.preventDefault()}
      >
        <div className="fuzzy-replace-head">
          <div>
            <span className="fuzzy-replace-title">Fix similar words</span>
            {matches.length > 0 ? (
              <span className="fuzzy-replace-count">{matches.length} found</span>
            ) : null}
          </div>
          <button
            type="button"
            className="fuzzy-replace-close"
            aria-label="Dismiss panel"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <p className="fuzzy-replace-hint">{hint}</p>

        <div className="fuzzy-replace-correction-card">
          <span className="fuzzy-replace-correction-label">Correction</span>
          <div className="fuzzy-replace-summary">
            <span className="fuzzy-replace-source" title="Original word">
              {trimmedSource || "—"}
            </span>
            <span className="fuzzy-replace-arrow" aria-hidden="true">
              →
            </span>
            <span
              className={`fuzzy-replace-target${correctionChanged ? "" : " pending"}`}
              title="Your correction"
            >
              {trimmedCorrection || "type here…"}
            </span>
          </div>
        </div>

        <div className="fuzzy-replace-slider-block">
          <div className="fuzzy-replace-slider-head">
            <span className="fuzzy-replace-slider-title">Match strictness</span>
            <span className="fuzzy-replace-slider-value">{minScore}%+</span>
          </div>
          <input
            type="range"
            className="fuzzy-replace-slider"
            min={FUZZY_MATCH_FLOOR}
            max={100}
            step={1}
            value={minScore}
            onChange={(e) => onMinScoreChange(Number(e.target.value))}
            aria-label="Match strictness"
          />
          <div className="fuzzy-replace-slider-ends">
            <span>Broader ({FUZZY_MATCH_FLOOR}%)</span>
            <span>Exact (100%)</span>
          </div>
        </div>

        <div className="fuzzy-replace-match-list">
          <div className="fuzzy-replace-match-head">
            <span>
              Similar matches
              {matches.length > 0 ? (
                <span className="fuzzy-replace-selection-count">
                  {" "}
                  · {selectedCount} of {matches.length} selected
                </span>
              ) : null}
            </span>
            {matches.length > 0 ? (
              <span className="fuzzy-replace-match-actions">
                <button type="button" className="fuzzy-replace-link-btn" onClick={onSelectAllMatches}>
                  All
                </button>
                <button type="button" className="fuzzy-replace-link-btn" onClick={onClearAllMatches}>
                  None
                </button>
              </span>
            ) : null}
          </div>
          {matches.length ? (
            <ul>
              {matches.map((m) => {
                const included = selectedMatchIndices.has(m.index);
                return (
                  <li key={m.index} className={included ? "" : "fuzzy-replace-match-excluded"}>
                    <div className="fuzzy-replace-match-row">
                      <label className="fuzzy-replace-match-check" title={included ? "Included in replace" : "Excluded from replace"}>
                        <input
                          type="checkbox"
                          checked={included}
                          onChange={(e) => onToggleMatch(m.index, e.target.checked)}
                        />
                      </label>
                      <button
                        type="button"
                        className="fuzzy-replace-match-btn"
                        onClick={() => onSeekToMatch(m.index)}
                        title={`Jump to ${formatMs(m.start_ms)} in transcript`}
                      >
                        <span className="fuzzy-replace-match-word">{m.text}</span>
                        <span className="fuzzy-replace-match-meta">
                          <span className={`fuzzy-replace-score ${scoreClass(m.score)}`}>
                            {m.score}%
                          </span>
                          <span className="fuzzy-replace-time">{formatMs(m.start_ms)}</span>
                        </span>
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="fuzzy-replace-empty muted">
              {correctionChanged
                ? "No similar words at this strictness."
                : "Matches appear after you type a correction."}
            </p>
          )}
        </div>

        {matches.length > 0 && selectedCount < matches.length ? (
          <p className="fuzzy-replace-excluded-note muted">
            {matches.length - selectedCount} match{matches.length - selectedCount === 1 ? "" : "es"}{" "}
            excluded — will not be changed.
          </p>
        ) : null}

        <div className="fuzzy-replace-actions">
          <button type="button" className="btn primary sm" disabled={!canReplace} onClick={onReplace}>
            {replaceLabel}
          </button>
        </div>

        <p className="fuzzy-replace-shortcuts muted">
          Check/uncheck matches · click word to jump · Enter saves this word only
        </p>
      </div>
    </>
  );
}
