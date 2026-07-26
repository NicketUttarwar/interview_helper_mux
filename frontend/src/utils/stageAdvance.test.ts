import { describe, expect, it, vi } from "vitest";
import { applyReuseResultAndFocus, readyForStageMessage } from "./stageAdvance";
import { invokeStepFooterSecondaryAction } from "./stageStepActions";
import type { RunData, StageStep } from "../types";
import { makeStage, makeStep } from "../test/runFixtures";

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
        makeStage("source_acoustic_profile", { title: "SAP", status: "done", phase: "understand" }),
        makeStage("interview_spine_build", { title: "Spine", status: "pending", phase: "understand" }),
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
        makeStage("source_acoustic_profile", { title: "SAP", status: "done", phase: "understand" }),
        makeStage("interview_spine_build", { title: "Spine", status: "pending", phase: "understand" }),
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

  it("shows transcript reuse toast only when server pending flag is set", async () => {
    const autoContinuePipeline = vi.fn().mockResolvedValue(true);
    const showToast = vi.fn();
    const run: RunData = {
      run_id: "exec_test",
      meta: { transcript_reuse_pending_edit: true },
      stages: [
        makeStage("transcribe", { title: "Transcribe", status: "done", phase: "prepare" }),
        makeStage("transcript_review_build", { title: "G0 build", status: "pending", phase: "prepare" }),
      ],
    };
    await applyReuseResultAndFocus({
      run,
      stageId: "transcribe",
      stageTitle: "Transcribe",
      reuse: { status: "reused", copied: ["transcript/full.json"], hasStagedWrites: false },
      refreshRun: vi.fn().mockResolvedValue(run),
      showToast,
      autoContinuePipeline,
      ...workbench,
    });
    expect(showToast).toHaveBeenCalledWith(
      "Reused prior Transcribe — review and edit the full transcript before continuing.",
      "success",
    );
    expect(autoContinuePipeline).not.toHaveBeenCalled();
    expect(workbench.selectStage).toHaveBeenCalled();
  });

  it("does not show transcript reuse toast when reuse was already applied", async () => {
    const autoContinuePipeline = vi.fn().mockResolvedValue(false);
    const showToast = vi.fn();
    const run: RunData = {
      run_id: "exec_test",
      meta: {
        stage_reuse: {
          transcribe: {
            action: "accept",
            applied_at: "2026-01-01T00:00:00Z",
          },
        },
      },
      stages: [
        makeStage("transcribe", { title: "Transcribe", status: "done", phase: "prepare" }),
        makeStage("transcript_review_build", { title: "G0 build", status: "pending", phase: "prepare" }),
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
      ...workbench,
    });
    expect(showToast).not.toHaveBeenCalledWith(
      "Reused prior Transcribe — review and edit the full transcript before continuing.",
      "success",
    );
    expect(showToast).toHaveBeenCalledWith(
      "Reused prior Transcribe outputs from ASSETS.",
      "success",
    );
  });

  it("does not open transcript edit interstitial for later transcript stages", async () => {
    const autoContinuePipeline = vi.fn().mockResolvedValue(false);
    const showToast = vi.fn();
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        makeStage("transcribe", { title: "Transcribe", status: "done", phase: "prepare" }),
        makeStage("transcript_review_build", { title: "G0 build", status: "done", phase: "prepare" }),
        makeStage("transcript_review", { title: "G0", status: "pending", phase: "prepare" }),
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
      ...workbench,
    });
    expect(showToast).not.toHaveBeenCalledWith(
      "Reused prior G0 build — review and edit the full transcript before continuing.",
      "success",
    );
  });
});

function reuseFreshStep(): StageStep {
  return makeStep("reuse", {
    number: 2,
    label: "Choose reuse or run fresh",
    primary_button: "Reuse outputs",
    secondary_button: "Run fresh instead",
    kind: "reuse",
  });
}

describe("invokeStepFooterSecondaryAction — global step actions", () => {
  it("run fresh instead declines reuse and runs", async () => {
    const declineReuseAndRun = vi.fn().mockResolvedValue(true);
    await invokeStepFooterSecondaryAction(reuseFreshStep(), makeStage("ingest", { title: "Ingest" }), {
      completeTranscriptReview: vi.fn(),
      skipOptional: vi.fn(),
      declineReuseAndRun,
      redoFromStage: vi.fn(),
    });
    expect(declineReuseAndRun).toHaveBeenCalledWith("ingest");
  });
});
