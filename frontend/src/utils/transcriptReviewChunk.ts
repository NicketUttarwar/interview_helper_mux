import type { TranscriptFocusRange, TranscriptReviewChunk } from "../types";

/** Playback window aligned with pre-cut review clip WAV boundaries. */
export function chunkPlaybackRange(chunk: TranscriptReviewChunk): {
  start_ms: number;
  end_ms: number;
} {
  return {
    start_ms: chunk.clip_start_ms ?? chunk.start_ms,
    end_ms: chunk.clip_end_ms ?? chunk.end_ms,
  };
}

export function chunkFocusRange(
  chunk: TranscriptReviewChunk,
  label: string,
): TranscriptFocusRange {
  const { start_ms, end_ms } = chunkPlaybackRange(chunk);
  return { start_ms, end_ms, label };
}

export function resolveChunkClipPath(chunk: TranscriptReviewChunk): string {
  if (chunk.clip_path) return chunk.clip_path;
  if (chunk.chunk_id) return `transcript/review_clips/${chunk.chunk_id}.wav`;
  return "";
}

export function chunkClipUrl(
  runId: string,
  chunk: TranscriptReviewChunk,
): string {
  const path = resolveChunkClipPath(chunk);
  if (!path) return "";
  if (chunk.clip_ready === false) return "";
  return `/api/runs/${runId}/audio?path=${encodeURIComponent(path)}`;
}
