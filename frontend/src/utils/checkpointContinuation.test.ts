import { describe, expect, it, vi } from "vitest";
import {
  advancePipeline,
  patchRunAfterWriteApproval,
  reconcileBusyRun,
  syncPipelineStageFocus,
  tryAutoContinuePipeline,
  tryAutopilotCheckpointResolution,
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
  it("builds complete job from nextStageId when server job lacks status", () => {
    const run = runStub({ journey: { phase: "prepare" } });
    const patched = patchRunAfterWriteApproval(run, {
      savedStageId: "audio_preclean",
      nextStageId: "ingest",
      job: { ok: true, run_id: "exec_test", mode: "stage" } as never,
    });
    expect(patched.job?.status).toBe("complete");
    expect(patched.job?.stage).toBe("audio_preclean");
    expect(patched.journey?.active_substep_id).toBe("run:ingest");
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

  it("focuses next runnable stage after write approval cleared without auto-run", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
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
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast,
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
    });
    expect(started).toBe(false);
    expect(executeJob).not.toHaveBeenCalled();
    expect(selectStage).toHaveBeenCalledWith("ingest", { stepId: "run" });
    expect(showToast).toHaveBeenCalledWith(
      "Ready for Ingest — use Run when you want to start.",
      "info",
    );
  });

  it("waits for handoff acknowledgment before running next stage", async () => {
    const acknowledgeHandoff = vi.fn().mockResolvedValue(undefined);
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        {
          id: "speaker_roles",
          title: "Speaker roles",
          status: "done",
          phase: "understand",
          handoff_paths: ["understanding/speakers.json"],
        },
        { id: "content_context", title: "Content context", status: "pending", phase: "understand" },
      ],
      job: { status: "complete", stage: "speaker_roles" },
    });
    const started = await advancePipeline({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "speaker_roles",
      executeJob,
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      autoRun: true,
      config: { journey_ui: { auto_advance_pipeline: true } },
      acknowledgeHandoff,
    });
    expect(started).toBe(false);
    expect(acknowledgeHandoff).not.toHaveBeenCalled();
    expect(executeJob).not.toHaveBeenCalled();
    expect(selectStage).toHaveBeenCalledWith("speaker_roles", { stepId: "handoff" });
  });

  it("auto-runs next stage when autopilot enabled", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
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
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast,
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      autoRun: true,
      config: { journey_ui: { auto_advance_pipeline: true } },
    });
    expect(started).toBe(true);
    expect(executeJob).toHaveBeenCalled();
    expect(selectStage).toHaveBeenCalledWith("ingest", { stepId: "run" });
    expect(showToast).not.toHaveBeenCalled();
  });
});

describe("syncPipelineStageFocus", () => {
  it("focuses reuse stage when SAP is done and spine has reuse blocking", async () => {
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        {
          id: "source_acoustic_profile",
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
        },
        {
          id: "interview_spine_build",
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        },
      ],
      handoff_ack: { source_acoustic_profile: "2026-01-01T00:00:00Z" },
      job: { status: "complete", stage: "source_acoustic_profile" },
      journey: {
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      },
    });
    const navigated = await syncPipelineStageFocus({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "source_acoustic_profile",
      executeJob: vi.fn(),
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      config: { journey_ui: { enabled: true } },
    });
    expect(navigated).toBe(true);
    expect(selectStage).toHaveBeenCalledWith("interview_spine_build", {
      stepId: "reuse",
      pinned: false,
    });
  });
});

describe("tryAutoContinuePipeline", () => {
  it("selects next stage without auto-run when stage_reuse blocks", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        {
          id: "source_acoustic_profile",
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
        },
        {
          id: "interview_spine_build",
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        },
      ],
      job: { status: "complete", stage: "source_acoustic_profile" },
      journey: {
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      },
    });
    await tryAutoContinuePipeline({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "source_acoustic_profile",
      completedStageId: "source_acoustic_profile",
      executeJob,
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      config: { journey_ui: { auto_advance_pipeline: true } },
    });
    expect(selectStage).toHaveBeenCalledWith("interview_spine_build", {
      stepId: "reuse",
      pinned: false,
    });
    expect(executeJob).not.toHaveBeenCalled();
  });

  it("waits for handoff acknowledgment before auto-continuing", async () => {
    const acknowledgeHandoff = vi.fn().mockResolvedValue(undefined);
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        {
          id: "source_acoustic_profile",
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
          handoff_paths: ["understanding/source_acoustic_profile.json"],
        },
        {
          id: "interview_spine_build",
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        },
      ],
      job: { status: "complete", stage: "source_acoustic_profile" },
    });
    const started = await tryAutoContinuePipeline({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "source_acoustic_profile",
      completedStageId: "source_acoustic_profile",
      executeJob,
      selectStage: vi.fn().mockResolvedValue(undefined),
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      acknowledgeHandoff,
      config: { journey_ui: { auto_advance_pipeline: true } },
    });
    expect(started).toBe(false);
    expect(acknowledgeHandoff).not.toHaveBeenCalled();
    expect(executeJob).not.toHaveBeenCalled();
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

describe("tryAutopilotCheckpointResolution", () => {
  it("calls fixAllAndContinueStage when needs_clarification", async () => {
    const fixAllAndContinueStage = vi.fn().mockResolvedValue(true);
    const run = runStub({
      stages: [
        {
          id: "boundary_detection",
          title: "Boundaries",
          status: "action_required",
          phase: "understand",
        },
      ],
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        can_fix_all: true,
        itr_blocking_count: 2,
      },
    });
    const ok = await tryAutopilotCheckpointResolution({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "boundary_detection",
      executeJob: vi.fn(),
      selectStage: vi.fn(),
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      config: { journey_ui: { auto_advance_pipeline: true, full_autopilot: false } },
      fixAllAndContinueStage,
    });
    expect(ok).toBe(true);
    expect(fixAllAndContinueStage).toHaveBeenCalledWith("boundary_detection");
  });
});
