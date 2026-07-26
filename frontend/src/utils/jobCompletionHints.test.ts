import { describe, expect, it } from "vitest";
import { jobCompletionHint } from "./jobCompletionHints";
import { makeRunFixture } from "../test/runFixtures";

describe("jobCompletionHint", () => {
  it("hints transcript review after transcript_review_build", () => {
    const hint = jobCompletionHint(
      "transcript_review_build",
      makeRunFixture({ stages: [] }),
    );
    expect(hint).toMatch(/Transcript review/i);
  });

  it("hints timeline unlock after segment_classification", () => {
    const hint = jobCompletionHint(
      "segment_classification",
      makeRunFixture({ stages: [], timeline_ready: true }),
    );
    expect(hint).toMatch(/Timeline unlocked/i);
  });
});
