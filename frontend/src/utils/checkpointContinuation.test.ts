import { describe, expect, it, vi } from "vitest";
import {
  advancePipeline,
  patchRunAfterWriteApproval,
  reconcileBusyRun,
} from "./checkpointContinuation";
import type { RunData } from "../types";

function runStub(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [
      { id: "audio_preclean", title: "Pre-clean", status: "awaiting_write_approval", phase: "prepare" },
      { id: "ingest", title: "Ingest", status: "pending", phase: "prepare" },
    ],
    job: {
      status: "awaiting_write_approval",
      pending_write_stage: "audio_preclean",
      pending_write_paths: ["preclean/isolated.wav"],
    },
    ...overrides,
  };
}

describe("patchRunAfterWriteApproval", () => {
  it("builds running job from nextStageId when server job lacks status", () => {
    const run = runStub();
    const patched = patchRunAfterWriteApproval(run, {
      savedStageId: "audio_preclean",
      nextStageId: "ingest",
      job: { ok: true, run_id: "exec_test", mode: "stage" } as never,
    });
    expect(patched.job?.status).toBe("running");
    expect(patched.job?.stage).toBe("ingest");
  });

  it("marks saved stage done and clears write approval job fields", () => {
    const run = runStub();
    const patched = patchRunAfterWriteApproval(run, {
      savedStageId: "audio_preclean",
      nextStageId: "ingest",
      job: { ok: true, status: "running", stage: "ingest" } as never,
    });
    expect(patched.stages.find((s) => s.id === "audio_preclean")?.status).toBe("done");
    expect(patched.job?.awaiting_write_approval).toBe(false);
    expect(patched.job?.pending_write_stage).toBeUndefined();
    expect(patched.job?.stage).toBe("ingest");
  });

  it("surfaces stage reuse blocker after save", () => {
    const run = runStub({ journey: { phase: "prepare" } });
    const patched = patchRunAfterWriteApproval(run, {
      savedStageId: "audio_preclean",
      nextStageId: "ingest",
      job: {
        ok: false,
        status: "needs_operator",
        stage: "ingest",
        needs_stage_reuse: true,
        message: "Reuse available",
      },
    });
    expect(patched.stages.find((s) => s.id === "audio_preclean")?.status).toBe("done");
    expect(patched.blocking?.reason).toBe("stage_reuse");
    expect(patched.journey?.blocking?.reason).toBe("stage_reuse");
    expect(patched.journey?.active_substep_id).toBe("stage_reuse:ingest");
  });
});

describe("advancePipeline", () => {
  it("focuses write approval step on stage tab when writes pending", async () => {
    const setActiveStepId = vi.fn();
    const setPipelineSubTab = vi.fn();
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub();
    const started = await advancePipeline({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "audio_preclean",
      executeJob: vi.fn(),
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setActiveStepId,
      setPipelineSubTab,
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
    });
    expect(started).toBe(false);
    expect(selectStage).toHaveBeenCalledWith("audio_preclean", { stepId: "write_approval" });
    expect(setPipelineSubTab).toHaveBeenCalledWith("stage");
    expect(setActiveStepId).toHaveBeenCalledWith("write_approval");
  });

  it("starts next runnable stage after write approval cleared", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        { id: "audio_preclean", title: "Pre-clean", status: "done", phase: "prepare" },
        { id: "ingest", title: "Ingest", status: "pending", phase: "prepare" },
      ],
      job: { status: "complete" },
    });
    const started = await advancePipeline({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "audio_preclean",
      executeJob,
      selectStage: vi.fn(),
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
    });
    expect(started).toBe(true);
    expect(executeJob).toHaveBeenCalledWith(
      { mode: "stage", stage: "ingest" },
      { source: "checkpoint_continue" },
    );
  });
});

describe("reconcileBusyRun", () => {
  it("clears when server job is idle", async () => {
    const result = await reconcileBusyRun({
      runId: "exec_test",
      syncJobRunning: vi.fn().mockResolvedValue({ status: "complete" }),
      refreshRun: vi.fn().mockResolvedValue(
        runStub({ job: { status: "complete" } }),
      ),
      startJobPoll: vi.fn(),
      setActivityLogTab: vi.fn(),
      showToast: vi.fn(),
      context: "save",
    });
    expect(result.jobRunning).toBe(false);
    expect(result.writeApprovalCleared).toBe(true);
  });

  it("starts poll when server job is running", async () => {
    const startJobPoll = vi.fn();
    const result = await reconcileBusyRun({
      runId: "exec_test",
      syncJobRunning: vi.fn().mockResolvedValue({
        status: "running",
        stage: "ingest",
        message: "Hashing",
      }),
      refreshRun: vi.fn(),
      startJobPoll,
      setActivityLogTab: vi.fn(),
      showToast: vi.fn(),
      context: "save",
    });
    expect(result.jobRunning).toBe(true);
    expect(startJobPoll).toHaveBeenCalled();
  });
});
