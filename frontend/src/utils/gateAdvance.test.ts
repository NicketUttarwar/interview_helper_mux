import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(import.meta.dirname, "..");
const GATES_DIR = join(ROOT, "components/gates");

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
  it("uses advancePipeline for checkpoint continuation behind shouldAdvanceAfterGatePost", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("advanceFromCheckpoint");
    expect(text).toContain("shouldAdvanceAfterGatePost");
    expect(text).toContain("advancePipeline");
    expect(text).toContain("readyForStageMessage");
    expect(text).not.toContain("approveWriteAndContinue");
  });
});

describe("HC-6 gate panels pass refreshed snapshot into shouldAdvanceAfterGatePost", () => {
  const panels = [
    "GapFramingGatePanel.tsx",
    "GapDeliveryPanel.tsx",
    "VoiceReferencePanel.tsx",
    "PickupSpeakerPanel.tsx",
    "VoPickupPanel.tsx",
  ];

  it.each(panels)("%s does not consult stale hook run", (file) => {
    const text = readFileSync(join(GATES_DIR, file), "utf8");
    expect(text).toContain("shouldAdvanceAfterGatePost");
    expect(text).not.toContain("shouldAdvanceAfterGatePost(run)");
    expect(text).toContain("shouldAdvanceAfterGatePost(refreshed");
  });
});

describe("D-02 gates may call advanceFromCheckpoint; ban raw pipeline continue", () => {
  const gateFiles = readdirSync(GATES_DIR).filter((f) => f.endsWith(".tsx"));

  it.each(gateFiles)("%s does not call advancePipeline or checkpoint_continue", (file) => {
    const text = readFileSync(join(GATES_DIR, file), "utf8");
    expect(text).not.toContain("advancePipeline");
    expect(text).not.toContain("checkpoint_continue");
  });
});

describe("D-03 mutators guard with shouldBlockOperatorActionsForJob", () => {
  const panels = [
    "components/gates/TimelineOptimizerPanel.tsx",
    "components/gates/AcousticProfilePanel.tsx",
    "components/gates/GapFramingGatePanel.tsx",
    "components/gates/GapDeliveryPanel.tsx",
    "components/gates/GListenPanel.tsx",
    "components/gates/ConversationStudioPanel.tsx",
  ];

  it.each(panels)("%s imports shouldBlockOperatorActionsForJob", (rel) => {
    const text = readFileSync(join(ROOT, rel), "utf8");
    expect(text).toContain("shouldBlockOperatorActionsForJob");
  });
});
