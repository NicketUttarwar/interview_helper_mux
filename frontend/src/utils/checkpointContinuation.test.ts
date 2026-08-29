import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import {
  advancePipeline,
  focusStageWorkbench,
  patchRunAfterWriteApproval,
  reconcileBusyRun,
  syncPipelineStageFocus,
  tryAutoContinuePipeline,
  tryAutopilotCheckpointResolution,
} from "./checkpointContinuation";
import type { RunData } from "../types";
import { makeGuidance, makeJourney, makeStage, makeStep } from "../test/runFixtures";
import { clearAutoNavLedgerForTests, markAutoNavConsumed, resetAutoNavLedgerIfServerChanged } from "./autoNavigationLedger";

afterEach(() => {
  clearAutoNavLedgerForTests();
});

beforeEach(() => {
  resetAutoNavLedgerIfServerChanged("test-server-session");
});

function runStub(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [
      makeStage("audio_preclean", {
        title: "Pre-clean",
        status: "awaiting_write_approval",
        phase: "prepare",
      }),
      makeStage("ingest", { title: "Ingest", status: "pending", phase: "prepare" }),
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
    const run = runStub({ journey: makeJourney({ phase: "prepare" }) });
    const patched = patchRunAfterWriteApproval(run, {
      savedStageId: "audio_preclean",
      nextStageId: "ingest",
      job: { mode: "stage" },
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
      job: { status: "running", stage: "ingest" },
    });
    expect(patched.stages.find((s) => s.id === "audio_preclean")?.status).toBe("done");
    expect(patched.job?.awaiting_write_approval).toBe(false);
    expect(patched.job?.pending_write_stage).toBeUndefined();
    expect(patched.job?.stage).toBe("ingest");
  });

  it("surfaces stage reuse blocker after save", () => {
    const run = runStub({ journey: makeJourney({ phase: "prepare" }) });
    const patched = patchRunAfterWriteApproval(run, {
      savedStageId: "audio_preclean",
      nextStageId: "ingest",
      job: {
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
  it("focuses next runnable stage when writes pending (v2 auto-commit)", async () => {
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
    expect(selectStage).toHaveBeenCalledWith("audio_preclean", { stepId: "run" });
    expect(setActiveStepId).not.toHaveBeenCalledWith("write_approval");
  });

  it("focuses next runnable stage after write approval cleared without auto-run", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    const run = runStub({
      stages: [
        makeStage("audio_preclean", { title: "Pre-clean", status: "done", phase: "prepare" }),
        makeStage("ingest", { title: "Ingest", status: "pending", phase: "prepare" }),
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

  it("auto-runs next stage when handoffs disabled (v2)", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        makeStage("speaker_roles", {
          title: "Speaker roles",
          status: "done",
          phase: "understand",
          handoff_paths: ["understanding/speakers.json"],
        }),
        makeStage("content_context", {
          title: "Content context",
          status: "pending",
          phase: "understand",
        }),
      ],
      job: { status: "complete", stage: "speaker_roles" },
      journey: makeJourney({
        first_try: { enabled: false },
        handoff: { handoff_between_stages_enabled: true },
      }),
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
    });
    expect(started).toBe(true);
    expect(executeJob).toHaveBeenCalled();
    expect(selectStage).toHaveBeenCalledWith("content_context", { stepId: "run" });
  });

  it("auto-runs next stage when autopilot enabled", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    const run = runStub({
      stages: [
        makeStage("audio_preclean", { title: "Pre-clean", status: "done", phase: "prepare" }),
        makeStage("ingest", { title: "Ingest", status: "pending", phase: "prepare" }),
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
        makeStage("source_acoustic_profile", {
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
        }),
        makeStage("interview_spine_build", {
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        }),
      ],
      handoff_ack: { source_acoustic_profile: "2026-01-01T00:00:00Z" },
      job: { status: "complete", stage: "source_acoustic_profile" },
      journey: makeJourney({
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      }),
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

  it("does not auto-navigate to the same stage step twice in one server session", async () => {
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        makeStage("source_acoustic_profile", {
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
        }),
        makeStage("interview_spine_build", {
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        }),
      ],
      journey: makeJourney({
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      }),
    });
    const opts = {
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
    };
    const first = await syncPipelineStageFocus(opts);
    expect(first).toBe(true);
    expect(selectStage).toHaveBeenCalledTimes(1);

    const second = await syncPipelineStageFocus({
      ...opts,
      selectedStageId: "source_acoustic_profile",
    });
    expect(second).toBe(false);
    expect(selectStage).toHaveBeenCalledTimes(1);
  });

  it("does not yank back when the user browses an earlier stage after one guide", async () => {
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        makeStage("ingest", { title: "Ingest", status: "done", phase: "prepare" }),
        makeStage("interview_spine_build", {
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        }),
      ],
      journey: makeJourney({
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      }),
    });
    const opts = {
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "ingest",
      executeJob: vi.fn(),
      selectStage,
      expandStage: vi.fn(),
      setActiveSubstepId: vi.fn(),
      setPipelineSubTab: vi.fn(),
      showToast: vi.fn(),
      refreshRun: vi.fn().mockResolvedValue(run),
      navigateToNextBlocker: vi.fn(),
      config: { journey_ui: { enabled: true } },
    };
    expect(await syncPipelineStageFocus(opts)).toBe(true);
    expect(selectStage).toHaveBeenCalledTimes(1);

    // Operator clicked back to ingest — auto-surface must not pull them again,
    // even if a different substep would resolve for the same source stage.
    const afterBrowse = await syncPipelineStageFocus({
      ...opts,
      selectedStageId: "ingest",
      run: {
        ...run,
        journey: {
          ...run.journey!,
          active_substep_id: "write_approval:interview_spine_build",
        },
      },
      refreshRun: vi.fn().mockResolvedValue({
        ...run,
        journey: {
          ...run.journey!,
          active_substep_id: "write_approval:interview_spine_build",
        },
      }),
    });
    expect(afterBrowse).toBe(false);
    expect(selectStage).toHaveBeenCalledTimes(1);
  });
});

describe("tryAutoContinuePipeline", () => {
  it("selects next stage without auto-run when stage_reuse blocks", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        makeStage("source_acoustic_profile", {
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
        }),
        makeStage("interview_spine_build", {
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        }),
      ],
      job: { status: "complete", stage: "source_acoustic_profile" },
      journey: makeJourney({
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      }),
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

  it("auto-continues when handoffs disabled (v2)", async () => {
    const executeJob = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      stages: [
        makeStage("source_acoustic_profile", {
          title: "Source acoustic profile",
          status: "done",
          phase: "understand",
          handoff_paths: ["understanding/source_acoustic_profile.json"],
        }),
        makeStage("interview_spine_build", {
          title: "Interview spine",
          status: "pending",
          phase: "understand",
        }),
      ],
      job: { status: "complete", stage: "source_acoustic_profile" },
      journey: makeJourney({
        first_try: { enabled: false },
        handoff: { handoff_between_stages_enabled: true },
      }),
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
      config: { journey_ui: { auto_advance_pipeline: true } },
    });
    expect(started).toBe(true);
    expect(executeJob).toHaveBeenCalled();
  });

  it("opens G0 after STT review prep even if transcript_review was already auto-surfaced", async () => {
    markAutoNavConsumed({ stageId: "transcript_review", stepId: "review_transcript" });
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const run = runStub({
      transcript_review_pending: true,
      stages: [
        makeStage("transcript_review_build", {
          title: "STT review prep",
          status: "done",
          phase: "prepare",
        }),
        makeStage("transcript_review", {
          title: "Transcript review",
          status: "action_required",
          phase: "prepare",
          guidance: makeGuidance({
            steps: [
              makeStep("review_transcript", {
                embed: "transcript_review",
                status: "todo",
              }),
            ],
          }),
        }),
      ],
      job: { status: "complete", stage: "transcript_review_build" },
      journey: makeJourney({
        phase: "prepare",
        next_action: "Complete transcript review (GUI)",
        blocking: {
          blocked: true,
          reason: "transcript_review",
          stage_id: "transcript_review",
          message: "Transcript review required",
        },
      }),
    });
    const navigated = await tryAutoContinuePipeline({
      run,
      runId: "exec_test",
      apiGrants: {},
      selectedStageId: "transcript_review_build",
      completedStageId: "transcript_review_build",
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
    expect(selectStage).toHaveBeenCalledWith("transcript_review", {
      stepId: "review_transcript",
      pinned: false,
    });
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
    expect(result.writeApprovalCleared).toBe(false);
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
  it("is disabled in v2 (operator checkpoints require manual action)", async () => {
    const run = runStub({
      stages: [
        makeStage("boundary_detection", {
          title: "Boundaries",
          status: "action_required",
          phase: "understand",
        }),
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
      config: { journey_ui: { auto_advance_pipeline: true } },
    });
    expect(ok).toBe(false);
  });
});

describe("focusStageWorkbench", () => {
  it("routes virtual investigation_queue focus to Story Board without selecting a stage", async () => {
    const selectStage = vi.fn().mockResolvedValue(undefined);
    const setPipelineSubTab = vi.fn();
    const stepId = await focusStageWorkbench({
      run: runStub(),
      stageId: "investigation_queue",
      selectStage,
      expandStage: vi.fn(),
      setPipelineSubTab,
      navigationIntent: "user_continue",
    });
    expect(stepId).toBeNull();
    expect(selectStage).not.toHaveBeenCalled();
    expect(setPipelineSubTab).toHaveBeenCalledWith("story");
  });
});
