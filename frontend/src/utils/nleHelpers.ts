import type { NleState, TimelineSegment, TranscriptWord, VoLine, WaveformPeaksData } from "../types";

export const SEGMENT_FLAG_LABELS: Record<string, string> = {
  starts_mid_thought: "Starts mid-thought — may need bridge",
  references_prior_missing: "References missing prior context",
  heavy_crosstalk: "Heavy crosstalk — listen carefully",
};

export type ReviewFilter =
  | "flagged"
  | "aside"
  | "redo"
  | "low_confidence"
  | "off_selection"
  | "qc_issue"
  | "all";

export interface TimelineFilters {
  type: string;
  speakerRole: string;
  inSelection: string;
  excluded: string;
  hasVo: string;
  hasFlags: string;
  search: string;
  hideNonMatching: boolean;
}

export const DEFAULT_TIMELINE_FILTERS: TimelineFilters = {
  type: "",
  speakerRole: "",
  inSelection: "",
  excluded: "",
  hasVo: "",
  hasFlags: "",
  search: "",
  hideNonMatching: false,
};

export function segmentManifestBounds(seg: TimelineSegment): { start: number; end: number } {
  return {
    start: seg._manifest_start_ms ?? seg.start_ms,
    end: seg._manifest_end_ms ?? seg.end_ms,
  };
}

export function segmentDurationMs(seg: TimelineSegment): number {
  return Math.max(0, seg.end_ms - seg.start_ms);
}

export function estimateTrimRemovedMs(seg: TimelineSegment): number {
  const bounds = segmentManifestBounds(seg);
  return Math.max(0, bounds.end - bounds.start - segmentDurationMs(seg));
}

export function segmentHasFlags(seg: TimelineSegment): boolean {
  return Array.isArray(seg.flags) && seg.flags.length > 0;
}

export function wordsInSegment(words: TranscriptWord[], seg: TimelineSegment): TranscriptWord[] {
  return words.filter((w) => w.start_ms >= seg.start_ms && w.end_ms <= seg.end_ms);
}

export function tightenEndMs(seg: TimelineSegment, words: TranscriptWord[]): number | null {
  const segWords = wordsInSegment(words, seg);
  if (!segWords.length) return null;
  return segWords[segWords.length - 1].end_ms + 50;
}

export function expandToSentenceEndMs(seg: TimelineSegment, words: TranscriptWord[]): number {
  const segWords = wordsInSegment(words, seg);
  if (!segWords.length) return seg.end_ms;
  const text = segWords.map((w) => w.text).join(" ");
  const punctRe = /[.!?]["')\]]*\s*$/;
  if (punctRe.test(text.trim())) return seg.end_ms;
  const lastWordEnd = segWords[segWords.length - 1].end_ms;
  const allWords = words.filter(
    (w) => w.start_ms >= seg.start_ms && w.start_ms <= seg.end_ms + 8000,
  );
  for (const w of allWords) {
    if (w.end_ms <= lastWordEnd) continue;
    if (/[.!?]/.test(w.text)) return w.end_ms + 50;
  }
  return seg.end_ms;
}

export function lowConfidenceSpans(
  words: TranscriptWord[],
  threshold: number,
): Array<{ start_ms: number; end_ms: number; segmentId?: string }> {
  const spans: Array<{ start_ms: number; end_ms: number }> = [];
  let cur: { start_ms: number; end_ms: number } | null = null;
  for (const w of words) {
    const low = w.confidence != null && w.confidence < threshold && !w.corrected;
    if (low) {
      if (!cur) cur = { start_ms: w.start_ms, end_ms: w.end_ms };
      else cur.end_ms = w.end_ms;
    } else if (cur) {
      spans.push(cur);
      cur = null;
    }
  }
  if (cur) spans.push(cur);
  return spans;
}

export function segmentIdForTime(segments: TimelineSegment[], ms: number): string | null {
  for (const seg of segments) {
    const id = seg.segment_id || seg._nle_label;
    if (!id) continue;
    if (ms >= seg.start_ms && ms < seg.end_ms) return id;
  }
  return null;
}

export function silenceTrimBounds(
  seg: TimelineSegment,
  waveform: WaveformPeaksData | null,
  words: TranscriptWord[],
  threshold = 0.08,
): { start: number; end: number } | null {
  const bounds = segmentManifestBounds(seg);
  const segWords = wordsInSegment(words, seg);
  let start = bounds.start;
  let end = bounds.end;

  if (waveform?.peaks?.length) {
    const peaks = waveform.peaks.filter(
      (p) => p.t_ms >= bounds.start && p.t_ms <= bounds.end,
    );
    const first = peaks.find((p) => p.peak >= threshold);
    const last = [...peaks].reverse().find((p) => p.peak >= threshold);
    if (first) start = Math.max(bounds.start, first.t_ms - 30);
    if (last) end = Math.min(bounds.end, last.t_ms + 80);
  } else if (segWords.length) {
    start = segWords[0].start_ms;
    end = segWords[segWords.length - 1].end_ms + 50;
  } else {
    return null;
  }

  if (end - start < 300) return null;
  return { start, end };
}

export function filterSegments(
  segments: TimelineSegment[],
  filters: TimelineFilters,
  ctx: {
    selectionOrder: string[];
    voLines: VoLine[];
    lowConfSegmentIds: Set<string>;
    qcSegmentIds: Set<string>;
  },
): TimelineSegment[] {
  const q = filters.search.trim().toLowerCase();
  return segments.filter((seg) => {
    const id = seg.segment_id || "";
    if (filters.type && seg.type !== filters.type) return false;
    if (filters.speakerRole && seg.speaker_role !== filters.speakerRole) return false;
    if (filters.inSelection === "yes" && !ctx.selectionOrder.includes(id)) return false;
    if (filters.inSelection === "no" && ctx.selectionOrder.includes(id)) return false;
    if (filters.excluded === "yes" && !seg._excluded) return false;
    if (filters.excluded === "no" && seg._excluded) return false;
    const hasVo = ctx.voLines.some((v) => v.targets_segment_id === id);
    if (filters.hasVo === "yes" && !hasVo) return false;
    if (filters.hasVo === "no" && hasVo) return false;
    if (filters.hasFlags === "yes" && !segmentHasFlags(seg)) return false;
    if (filters.hasFlags === "no" && segmentHasFlags(seg)) return false;
    if (q && !(seg.text || "").toLowerCase().includes(q) && !id.toLowerCase().includes(q)) {
      return false;
    }
    return true;
  });
}

export function reviewQueueForFilter(
  filter: ReviewFilter,
  segments: TimelineSegment[],
  ctx: {
    selectionOrder: string[];
    lowConfSegmentIds: Set<string>;
    qcSegmentIds: Set<string>;
  },
): TimelineSegment[] {
  switch (filter) {
    case "flagged":
      return segments.filter((s) => segmentHasFlags(s) && !s._excluded);
    case "aside":
      return segments.filter((s) => s.type === "aside" && !s._excluded);
    case "redo":
      return segments.filter((s) => s._mark_redo && !s._excluded);
    case "low_confidence":
      return segments.filter((s) => {
        const id = s.segment_id || "";
        return ctx.lowConfSegmentIds.has(id) && !s._excluded;
      });
    case "off_selection":
      return segments.filter((s) => {
        const id = s.segment_id || "";
        return id && !ctx.selectionOrder.includes(id) && !s._excluded;
      });
    case "qc_issue":
      return segments.filter((s) => {
        const id = s.segment_id || "";
        return ctx.qcSegmentIds.has(id);
      });
    default:
      return segments.filter((s) => !s._excluded);
  }
}

export function describeHistoryEntry(
  prev: NleState | null,
  next: NleState,
  label?: string,
): string {
  if (label) return label;
  const pOv = prev?.segment_overrides || {};
  const nOv = next.segment_overrides || {};
  const allIds = new Set([...Object.keys(pOv), ...Object.keys(nOv)]);
  for (const id of allIds) {
    const p = pOv[id] || {};
    const n = nOv[id] || {};
    if (n.excluded && !p.excluded) return `Excluded ${id}`;
    if (!n.excluded && p.excluded) return `Restored ${id}`;
    if (n.mark_redo && !p.mark_redo) return `Marked redo ${id}`;
    if ((n.start_ms != null || n.end_ms != null) && (p.start_ms !== n.start_ms || p.end_ms !== n.end_ms)) {
      return `Trimmed ${id}`;
    }
  }
  const pOrder = JSON.stringify(prev?.sequence_order || []);
  const nOrder = JSON.stringify(next.sequence_order || []);
  if (pOrder !== nOrder) return "Reordered segments";
  return "Timeline edit";
}

export function parseSegmentIdFromQcMessage(msg: string): string | null {
  const m = msg.match(/\b(seg_[a-z0-9_]+)\b/i);
  return m ? m[1] : null;
}
