import { describe, expect, it, vi } from "vitest";
import { invokeStepFooterSecondaryAction } from "./stageStepActions";
import type { StageInfo, StageStep } from "../types";

function stage(id: string): StageInfo {
  return { id, title: id, status: "pending", phase: "prepare" };
}

function precleanSkipStep(): StageStep {
  return {
    id: "review_offer",
    number: 1,
    title: "Review the pre-clean offer",
    instruction: "",
    review: [],
    primary_button: "Run audio cleaning",
    secondary_button: "Skip this optional step",
    kind: "preclean",
    status: "todo",
  };
}

describe("invokeStepFooterSecondaryAction", () => {
  it("skip optional preclean calls skipOptional handler", async () => {
    const skipOptional = vi.fn().mockResolvedValue(undefined);
    await invokeStepFooterSecondaryAction(precleanSkipStep(), stage("audio_preclean"), {
      discardPendingWrites: vi.fn(),
      completeTranscriptReview: vi.fn(),
      skipOptional,
      declineReuseAndRun: vi.fn(),
      redoFromStage: vi.fn(),
    });
    expect(skipOptional).toHaveBeenCalledWith("audio_preclean");
  });

  it("redo from this step calls redoFromStage", async () => {
    const redoFromStage = vi.fn().mockResolvedValue(undefined);
    const step: StageStep = {
      id: "complete",
      number: 4,
      title: "Step complete",
      instruction: "",
      review: [],
      primary_button: "Continue",
      secondary_button: "Redo from this step",
      kind: "done",
      status: "done",
    };
    await invokeStepFooterSecondaryAction(step, stage("ingest", "Ingest"), {
      discardPendingWrites: vi.fn(),
      completeTranscriptReview: vi.fn(),
      skipOptional: vi.fn(),
      declineReuseAndRun: vi.fn(),
      redoFromStage,
    });
    expect(redoFromStage).toHaveBeenCalled();
  });
});
