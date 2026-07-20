import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(import.meta.dirname, "..");

describe("gate panels use StageStepFooter for checkpoint actions", () => {
  it("StageStepFooter wires v2 gate completion actions", () => {
    const footer = readFileSync(join(ROOT, "components/workspace/StageStepFooter.tsx"), "utf8");
    expect(footer).toContain("completeTranscriptReview");
    expect(footer).toContain("approveSfxPrompts");
    expect(footer).toContain("declineReuseAndRun");
    expect(footer).toContain("skipOptionalStage");
    expect(footer).toContain("advanceFromCheckpoint");
    expect(footer).not.toContain("completeDisfluencyReview");
    expect(footer).not.toContain("approveWriteAndContinue");
  });
});

describe("advanceFromCheckpoint chains advancePipeline", () => {
  it("uses advancePipeline for checkpoint continuation", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("advanceFromCheckpoint");
    expect(text).toContain("advancePipeline");
    expect(text).toContain("readyForStageMessage");
    expect(text).not.toContain("approveWriteAndContinue");
  });
});
