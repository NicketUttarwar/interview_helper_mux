import { describe, expect, it, vi } from "vitest";
import { applyReuseResultAndFocus, readyForStageMessage } from "./stageAdvance";
import { invokeStepFooterSecondaryAction } from "./stageStepActions";
import type { RunData, StageInfo, StageStep } from "../types";

describe("readyForStageMessage", () => {
  it("uses consistent manual-run wording", () => {
    expect(readyForStageMessage("Ingest")).toBe(
      "Ready for Ingest — use Run when you want to start.",
    );
  });
});

describe("applyReuseResultAndFocus", () => {
  const workbench = {
    selectStage: vi.fn().mockResolvedValue(undefined),
    expandStage: vi.fn(),
    setActiveStepId: vi.fn(),
    setPipelineSubTab: vi.fn(),
  };

  it("chains autopilot after reuse without staged writes", async () => {
    const autoContinuePipeline = vi.fn().mockResolvedValue(true);
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        { id: "source_acoustic_profile", title: "SAP", status: "done", phase: "understand" },
        { id: "interview_spine_build", title: "Spine", status: "pending", phase: "understand" },
      ],
    };
    await applyReuseResultAndFocus({
      run,
      stageId: "source_acoustic_profile",
      stageTitle: "SAP",
      reuse: { status: "reused", copied: [], hasStagedWrites: false },
      refreshRun: vi.fn().mockResolvedValue(run),
      showToast: vi.fn(),
      autoContinuePipeline,
      ...workbench,
    });
    expect(autoContinuePipeline).toHaveBeenCalledWith("source_acoustic_profile");
  });

  it("focuses next stage when autopilot does not continue", async () => {
    const autoContinuePipeline = vi.fn().mockResolvedValue(false);
    const showToast = vi.fn();
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        { id: "source_acoustic_profile", title: "SAP", status: "done", phase: "understand" },
        { id: "interview_spine_build", title: "Spine", status: "pending", phase: "understand" },
      ],
    };
    await applyReuseResultAndFocus({
      run,
      stageId: "source_acoustic_profile",
      stageTitle: "SAP",
      reuse: { status: "reused", copied: [], hasStagedWrites: false },
      refreshRun: vi.fn().mockResolvedValue(run),
      showToast,
      autoContinuePipeline,
      ...workbench,
    });
    expect(workbench.selectStage).toHaveBeenCalledWith("interview_spine_build", { stepId: "run" });
    expect(showToast).toHaveBeenCalledWith(
      "Ready for Spine — use Run when you want to start.",
      "info",
    );
  });

  it("opens transcript edit interstitial and does not auto-continue", async () => {
    const autoContinuePipeline = vi.fn().mockResolvedValue(true);
    const openTranscriptReuseEdit = vi.fn();
    const showToast = vi.fn();
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        { id: "transcribe", title: "Transcribe", status: "done", phase: "prepare" },
        { id: "transcript_review_build", title: "G0 build", status: "pending", phase: "prepare" },
      ],
    };
    await applyReuseResultAndFocus({
      run,
      stageId: "transcribe",
      stageTitle: "Transcribe",
      reuse: { status: "reused", copied: [], hasStagedWrites: false },
      refreshRun: vi.fn().mockResolvedValue(run),
      showToast,
      autoContinuePipeline,
      openTranscriptReuseEdit,
      ...workbench,
    });
    expect(openTranscriptReuseEdit).toHaveBeenCalled();
    expect(autoContinuePipeline).not.toHaveBeenCalled();
    expect(workbench.selectStage).toHaveBeenCalled();
  });

  it("does not open transcript edit interstitial for later transcript stages", async () => {
    const openTranscriptReuseEdit = vi.fn();
    const autoContinuePipeline = vi.fn().mockResolvedValue(false);
    const showToast = vi.fn();
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        { id: "transcribe", title: "Transcribe", status: "done", phase: "prepare" },
        {
          id: "transcript_review_build",
          title: "G0 build",
          status: "done",
          phase: "prepare",
        },
        { id: "transcript_review", title: "G0", status: "pending", phase: "prepare" },
      ],
    };
    await applyReuseResultAndFocus({
      run,
      stageId: "transcript_review_build",
      stageTitle: "G0 build",
      reuse: { status: "reused", copied: [], hasStagedWrites: false },
      refreshRun: vi.fn().mockResolvedValue(run),
      showToast,
      autoContinuePipeline,
      openTranscriptReuseEdit,
      ...workbench,
    });
    expect(openTranscriptReuseEdit).not.toHaveBeenCalled();
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
