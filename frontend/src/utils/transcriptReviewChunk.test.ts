import { describe, expect, it } from "vitest";
import {
  chunkClipUrl,
  chunkFocusRange,
  chunkPlaybackRange,
  resolveChunkClipPath,
} from "./transcriptReviewChunk";

describe("transcriptReviewChunk", () => {
  const chunk = {
    chunk_id: "chunk_001",
    start_ms: 1000,
    end_ms: 2000,
    clip_start_ms: 950,
    clip_end_ms: 2100,
    clip_path: "transcript/review_clips/chunk_001.wav",
  };

  it("uses clip boundaries for playback range", () => {
    expect(chunkPlaybackRange(chunk)).toEqual({ start_ms: 950, end_ms: 2100 });
  });

  it("builds focus range from clip boundaries", () => {
    expect(chunkFocusRange(chunk, "Clip #1")).toEqual({
      start_ms: 950,
      end_ms: 2100,
      label: "Clip #1",
    });
  });

  it("infers clip path from chunk id", () => {
    expect(resolveChunkClipPath({ chunk_id: "chunk_002", start_ms: 0, end_ms: 1 })).toBe(
      "transcript/review_clips/chunk_002.wav",
    );
  });

  it("omits clip url when clip_ready is false", () => {
    expect(
      chunkClipUrl("exec_test", {
        ...chunk,
        clip_ready: false,
      }),
    ).toBe("");
  });
});
