import { describe, expect, it } from "vitest";
import {
  disfluencyClipUrl,
  firstPendingEventIndex,
  resolveDisfluencyClipPath,
} from "./disfluencyReviewEvent";

describe("disfluencyReviewEvent", () => {
  it("resolves clip path from event id when clip_path missing", () => {
    expect(resolveDisfluencyClipPath({ event_id: "fill_0002" })).toBe(
      "transcript/disfluency_clips/fill_0002.wav",
    );
  });

  it("builds audio URL for run clip", () => {
    expect(
      disfluencyClipUrl("exec_test", {
        event_id: "fill_0001",
        clip_path: "transcript/disfluency_clips/fill_0001.wav",
      }),
    ).toBe("/api/runs/exec_test/audio?path=transcript%2Fdisfluency_clips%2Ffill_0001.wav");
  });

  it("jumps to first pending event", () => {
    const events = [
      { review_status: "confirmed" },
      { review_status: "pending" },
      { review_status: "pending" },
    ];
    expect(firstPendingEventIndex(events)).toBe(1);
  });
});
