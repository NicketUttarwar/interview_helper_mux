import { describe, expect, it } from "vitest";
import { jobCompletionHint } from "./jobCompletionHints";
import type { RunData } from "../types";

describe("jobCompletionHint", () => {
  it("hints transcript review after transcript_review_build", () => {
    const hint = jobCompletionHint("transcript_review_build", { stages: [] } as RunData);
    expect(hint).toMatch(/Transcript review/i);
  });

  it("hints timeline unlock after segment_classification", () => {
    const hint = jobCompletionHint("segment_classification", {
      stages: [],
      timeline_ready: true,
    } as RunData);
    expect(hint).toMatch(/Timeline unlocked/i);
  });
});
