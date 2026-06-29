import { describe, expect, it } from "vitest";
import { recordAutoContinue, shouldSkipDuplicateAutoContinue } from "./autoContinueDedupe";

describe("autoContinueDedupe", () => {
  it("skips duplicate within window", () => {
    const last = recordAutoContinue("ingest", 1000);
    expect(shouldSkipDuplicateAutoContinue("ingest", last, 2000)).toBe(true);
    expect(shouldSkipDuplicateAutoContinue("ingest", last, 6000)).toBe(false);
  });

  it("does not skip different stages", () => {
    const last = recordAutoContinue("ingest", 1000);
    expect(shouldSkipDuplicateAutoContinue("transcribe", last, 1500)).toBe(false);
  });
});
