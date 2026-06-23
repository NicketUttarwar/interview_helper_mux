import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(import.meta.dirname, "..");

const GATE_PANELS = [
  "components/gates/TranscriptReviewPanel.tsx",
  "components/gates/DisfluencyReviewPanel.tsx",
  "components/gates/VoPickupPanel.tsx",
  "components/gates/FlowSelectPanel.tsx",
  "components/gates/AnalysisProfileGate.tsx",
  "components/gates/SfxPromptReviewPanel.tsx",
  "components/gates/SfxPostListenPanel.tsx",
] as const;

describe("gate panels use advanceFromCheckpoint", () => {
  it.each(GATE_PANELS)("%s", (rel) => {
    const text = readFileSync(join(ROOT, rel), "utf8");
    expect(text).toContain("advanceFromCheckpoint");
  });
});

describe("approveWriteAndContinue chains advancePipeline", () => {
  it("clears actionBusy before advancePipeline", () => {
    const text = readFileSync(join(ROOT, "context/AppContext.tsx"), "utf8");
    expect(text).toContain("approveWriteAndContinue");
    expect(text).toMatch(/actionBusyRef\.current = false[\s\S]*advancePipeline/);
    expect(text).toContain("checkpoint_continue");
  });
});
