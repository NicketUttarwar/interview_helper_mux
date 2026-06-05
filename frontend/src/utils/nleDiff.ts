import type { NleState, TimelineSegment, VoLine } from "../types";
import { segmentManifestBounds } from "./nleHelpers";

export interface NleDiffSummary {
  excludedCount: number;
  redoCount: number;
  trimmedCount: number;
  reordered: boolean;
  splitCount: number;
  msRemoved: number;
  voConflictIds: string[];
  chapterConflictIds: string[];
}

export function computeNleDiff(
  segments: TimelineSegment[],
  nle: NleState | null,
  ctx?: {
    voLines?: VoLine[];
    chapterAnchorIds?: string[];
  },
): NleDiffSummary {
  const overrides = nle?.segment_overrides || {};
  let excludedCount = 0;
  let redoCount = 0;
  let trimmedCount = 0;
  let splitCount = 0;
  let msRemoved = 0;
  const voConflictIds: string[] = [];
  const chapterConflictIds: string[] = [];
  const excludedIds = new Set<string>();

  for (const seg of segments) {
    const id = seg.segment_id;
    if (!id) continue;
    const ov = overrides[id] || {};
    if (ov.excluded || seg._excluded) {
      excludedCount += 1;
      excludedIds.add(id);
    }
    if (ov.mark_redo || seg._mark_redo) redoCount += 1;
    if (ov.split_into) splitCount += 1;
    const bounds = segmentManifestBounds(seg);
    const curStart = ov.start_ms != null ? Number(ov.start_ms) : seg.start_ms;
    const curEnd = ov.end_ms != null ? Number(ov.end_ms) : seg.end_ms;
    const manifestDur = bounds.end - bounds.start;
    const curDur = curEnd - curStart;
    if (curDur < manifestDur - 20) {
      trimmedCount += 1;
      msRemoved += manifestDur - curDur;
    }
  }

  const reordered = Boolean(nle?.sequence_order?.length);

  for (const line of ctx?.voLines || []) {
    if (excludedIds.has(line.targets_segment_id)) {
      voConflictIds.push(line.line_id);
    }
  }
  for (const anchor of ctx?.chapterAnchorIds || []) {
    if (excludedIds.has(anchor)) chapterConflictIds.push(anchor);
  }

  return {
    excludedCount,
    redoCount,
    trimmedCount,
    reordered,
    splitCount,
    msRemoved,
    voConflictIds,
    chapterConflictIds,
  };
}
