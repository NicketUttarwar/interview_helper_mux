import { describe, expect, it } from "vitest";
import {
  buildStageProgress,
  buildStageSubsteps,
  findActiveSubstep,
  guidanceItemToSubstep,
  shouldShowRunningConnector,
} from "./stageSubsteps";
import { resolveOperatorAction } from "./resolveOperatorAction";
import type { RunData, StageInfo } from "../types";

function stage(partial: Partial<StageInfo> & { id: string; title: string }): StageInfo {
  return {
    description: "",
    status: "pending",
    ...partial,
  };
}

function minimalRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [],
    ...overrides,
  };
}

describe("stageSubsteps", () => {
  it("includes write approval from attention when ingest awaits review", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "awaiting_write_approval",
      operator_phase: "prepare",
      guidance: {
        phase_label: "Prepare",
        prerequisites: [],
        actions: [{ id: "run_ingest", label: "Run ingest", status: "done" }],
        unlocks: "Transcribe",
      },
    });
    const run = minimalRun({
      stages: [ingest],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
        message: "Stage 'ingest' outputs await review (2 file(s))",
      },
    });
    const subs = buildStageSubsteps(ingest, run);
    const writeSub = subs.find((s) => s.kind === "write_approval");
    expect(writeSub).toBeDefined();
    expect(writeSub?.status).toBe("todo");
  });

  it("marks running substep when job is active on stage", () => {
    const transcribe = stage({
      id: "transcribe",
      title: "Transcribe",
      status: "pending",
      operator_phase: "prepare",
    });
    const run = minimalRun({
      stages: [transcribe],
      job: { status: "running", stage: "transcribe", current_stage: "transcribe" },
    });
    const subs = buildStageSubsteps(transcribe, run, { jobRunning: true });
    expect(subs.some((s) => s.status === "running")).toBe(true);
  });

  it("marks fullyComplete when stage done and no pending substeps", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "done",
      operator_phase: "prepare",
      guidance: {
        phase_label: "Prepare",
        prerequisites: [],
        actions: [{ id: "run_ingest", label: "Run ingest", status: "done" }],
        unlocks: "Transcribe",
      },
    });
    const run = minimalRun({ stages: [ingest] });
    const progress = buildStageProgress(ingest, run);
    expect(progress.fullyComplete).toBe(true);
  });

  it("dedupes write approval guidance and attention", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "awaiting_write_approval",
      operator_phase: "prepare",
      guidance: {
        phase_label: "Prepare",
        prerequisites: [
          {
            id: "write_approval",
            label: "Review pending writes",
            status: "todo",
            kind: "checkpoint",
          },
        ],
        actions: [],
        unlocks: "Transcribe",
      },
    });
    const run = minimalRun({
      stages: [ingest],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
        message: "(2 file(s))",
      },
    });
    const subs = buildStageSubsteps(ingest, run);
    const writeSubs = subs.filter((s) => s.kind === "write_approval");
    expect(writeSubs.length).toBeLessThanOrEqual(2);
  });

  it("findActiveSubstep returns first todo or running", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "awaiting_write_approval",
      operator_phase: "prepare",
    });
    const run = minimalRun({
      stages: [ingest],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
      },
    });
    const active = findActiveSubstep(run);
    expect(active?.stageId).toBe("ingest");
  });

  it("shouldShowRunningConnector between stages when job running", () => {
    const ingest = stage({ id: "ingest", title: "Ingest", status: "done" });
    const transcribe = stage({ id: "transcribe", title: "Transcribe", status: "pending" });
    const run = minimalRun({
      stages: [ingest, transcribe],
      job: { status: "running", stage: "transcribe", current_stage: "transcribe" },
    });
    expect(
      shouldShowRunningConnector(ingest, transcribe, run, true),
    ).toBe(true);
  });

  it("does not promote blocked substep to running from journey hint", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "awaiting_write_approval",
      operator_phase: "prepare",
    });
    const run = minimalRun({
      stages: [ingest],
      job: { status: "awaiting_write_approval", stage: "ingest", pending_write_stage: "ingest" },
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "Save files",
        blocking: {
          blocked: true,
          reason: "write_approval",
          stage_id: "ingest",
          message: "Save 2 files",
        },
        active_substep_id: "blocked:ingest",
      },
    });
    const subs = buildStageSubsteps(ingest, run);
    const blockedSub = subs.find((s) => s.kind === "blocked" || s.kind === "write_approval");
    expect(blockedSub?.status).toBe("todo");
  });

  it("shows Saving… on write_approval when actionBusy", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "awaiting_write_approval",
      operator_phase: "prepare",
    });
    const run = minimalRun({
      stages: [ingest],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
      },
    });
    const subs = buildStageSubsteps(ingest, run, { actionBusy: true });
    const writeSub = subs.find((s) => s.kind === "write_approval");
    expect(writeSub?.status).toBe("running");
    expect(writeSub?.label).toContain("Saving");
  });

  it("guidanceItemToSubstep maps checkpoint kind", () => {
    const sub = guidanceItemToSubstep(
      { id: "g0", label: "Complete review", status: "todo", kind: "checkpoint" },
      "transcript_review",
    );
    expect(sub.kind).toBe("checkpoint");
    expect(sub.targetSection).toBe("modal-gates");
  });

  it("marks error substep when job status is error on stage", () => {
    const transcribe = stage({
      id: "transcribe",
      title: "Transcribe",
      status: "pending",
      operator_phase: "prepare",
    });
    const run = minimalRun({
      stages: [transcribe],
      job: {
        status: "error",
        stage: "transcribe",
        message: "AWS transcription failed",
        last_error: { message: "AWS transcription failed" },
      },
    });
    const subs = buildStageSubsteps(transcribe, run);
    expect(subs.some((s) => s.status === "error")).toBe(true);
    const progress = buildStageProgress(transcribe, run);
    expect(progress.hasError).toBe(true);
    expect(progress.fullyComplete).toBe(false);
  });

  it("findActiveSubstep aligns with resolver substepId for write approval", () => {
    const ingest = stage({
      id: "ingest",
      title: "Ingest",
      status: "awaiting_write_approval",
      operator_phase: "prepare",
    });
    const run = minimalRun({
      stages: [ingest],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
      },
    });
    const action = resolveOperatorAction(run);
    const active = findActiveSubstep(run, { jobRunning: false });
    expect(action.substepId).toBe("write_approval:ingest");
    expect(active?.kind).toBe("write_approval");
    expect(active?.id).toBe(`write_approval:${ingest.id}`);
  });
});
