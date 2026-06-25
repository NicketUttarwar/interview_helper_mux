import { describe, expect, it, vi } from "vitest";
import { readyForStageMessage } from "./stageAdvance";
import { invokeStepFooterSecondaryAction } from "./stageStepActions";
import type { StageInfo, StageStep } from "../types";

describe("readyForStageMessage", () => {
  it("uses consistent manual-run wording", () => {
    expect(readyForStageMessage("Ingest")).toBe(
      "Ready for Ingest — use Run when you want to start.",
    );
  });
});

function stage(id: string, title = id): StageInfo {
  return { id, title, status: "pending", phase: "prepare" };
}

function reuseFreshStep(): StageStep {
  return {
    id: "reuse",
    number: 2,
    title: "Choose reuse or run fresh",
    instruction: "",
    review: [],
    primary_button: "Reuse outputs",
    secondary_button: "Run fresh instead",
    kind: "reuse",
    status: "todo",
  };
}

describe("invokeStepFooterSecondaryAction — global step actions", () => {
  it("run fresh instead declines reuse and runs", async () => {
    const declineReuseAndRun = vi.fn().mockResolvedValue(undefined);
    await invokeStepFooterSecondaryAction(reuseFreshStep(), stage("ingest", "Ingest"), {
      discardPendingWrites: vi.fn(),
      completeTranscriptReview: vi.fn(),
      skipOptional: vi.fn(),
      declineReuseAndRun,
      redoFromStage: vi.fn(),
    });
    expect(declineReuseAndRun).toHaveBeenCalledWith("ingest");
  });
});
