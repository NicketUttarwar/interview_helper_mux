import { describe, expect, it, vi } from "vitest";
import { advancePipeline, reconcileBusyRun } from "./checkpointContinuation";
import type { RunData } from "../types";

function runStub(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [
      { id: "audio_preclean", title: "Pre-clean", status: "done", phase: "prepare" },
      { id: "ingest", title: "Ingest", status: "pending", phase: "prepare" },
    ],
    ...overrides,
  };
}

describe("advancePipeline", () => {
  it("starts next runnable stage after write approval cleared", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const run = runStub({ job: { status: "complete" } });
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
