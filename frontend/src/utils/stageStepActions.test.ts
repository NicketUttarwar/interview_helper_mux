import { describe, expect, it, vi } from "vitest";
import { invokeStepFooterSecondaryAction } from "./stageStepActions";
import type { StageInfo, StageStep } from "../types";
import { makeStage, makeStep } from "../test/runFixtures";

function stage(id: string): StageInfo {
  return makeStage(id, { phase: "prepare" });
}

function precleanSkipStep(): StageStep {
  return makeStep("review_offer", {
    label: "Review the pre-clean offer",
    primary_button: "Run audio cleaning",
    secondary_button: "Skip this optional step",
    kind: "preclean",
  });
}

describe("invokeStepFooterSecondaryAction", () => {
  it("skip optional preclean calls skipOptional handler", async () => {
    const skipOptional = vi.fn().mockResolvedValue(undefined);
    await invokeStepFooterSecondaryAction(precleanSkipStep(), stage("audio_preclean"), {
      completeTranscriptReview: vi.fn(),
      skipOptional,
      declineReuseAndRun: vi.fn(),
      redoFromStage: vi.fn(),
    });
    expect(skipOptional).toHaveBeenCalledWith("audio_preclean");
  });

  it("redo from this step calls redoFromStage", async () => {
    const redoFromStage = vi.fn().mockResolvedValue(undefined);
    const step: StageStep = makeStep("complete", {
      number: 4,
      label: "Step complete",
      primary_button: "Continue",
      secondary_button: "Redo from this step",
      kind: "done",
      status: "done",
    });
    await invokeStepFooterSecondaryAction(step, stage("ingest"), {
      completeTranscriptReview: vi.fn(),
      skipOptional: vi.fn(),
      declineReuseAndRun: vi.fn(),
      redoFromStage,
    });
    expect(redoFromStage).toHaveBeenCalled();
  });
});
