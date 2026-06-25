import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(import.meta.dirname, "..");

const PROFILE_CHECKPOINT_CONSUMERS = [
  "components/gates/AnalysisProfileGate.tsx",
  "components/workspace/ProfilePanel.tsx",
  "components/workspace/StoryBoardPanel.tsx",
] as const;

describe("gate panels use StageStepFooter for checkpoint actions", () => {
  it("StageStepFooter wires gate completion and reuse actions", () => {
    const footer = readFileSync(join(ROOT, "components/workspace/StageStepFooter.tsx"), "utf8");
    expect(footer).toContain("completeTranscriptReview");
    expect(footer).toContain("completeDisfluencyReview");
    expect(footer).toContain("approveSfxPrompts");
    expect(footer).toContain("declineReuseAndRun");
    expect(footer).toContain("skipOptionalStage");
    expect(footer).toContain("advanceFromCheckpoint");
  });
});

describe("analysis profile panels use shared checkpoint helper", () => {
  it.each(PROFILE_CHECKPOINT_CONSUMERS)("%s", (rel) => {
    const text = readFileSync(join(ROOT, rel), "utf8");
    expect(text).toContain("completeAnalysisProfile");
  });
});

describe("approveWriteAndContinue chains advancePipeline", () => {
  it("uses continue-after-checkpoint for atomic save and advance", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("approveWriteAndContinue");
    expect(text).toContain("continue-after-checkpoint");
    expect(text).toContain("advancePipeline");
    expect(text).toContain("readyForStageMessage");
  });
});
