import { describe, expect, it, beforeEach } from "vitest";
import type { RunData } from "../types";
import {
  canAttemptAutopilotCheckpoint,
  canAttemptAutopilotFixAll,
  clearAutopilotCheckpointAttempts,
  recordAutopilotFixAllAttempt,
  recordAutopilotWriteApprovalAttempt,
  resolveAutopilotCheckpoint,
  autopilotHidesReviewGate,
} from "./autopilotResolution";

function runStub(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [{ id: "boundary_detection", title: "Boundaries", status: "action_required", phase: "understand" }],
    ...overrides,
  };
}

const legacyConfig = { journey_ui: { full_autopilot: false } } as const;

describe("autopilotResolution", () => {
  beforeEach(() => {
    clearAutopilotCheckpointAttempts("exec_test", "boundary_detection");
  });

  it("does not resolve fix_all while clarification is deferred", () => {
    const run = runStub({
      job: {
        status: "running",
        stage: "boundary_detection",
        clarification_pending: true,
        can_fix_all: true,
        itr_blocking_count: 1,
      },
    });
    expect(resolveAutopilotCheckpoint(run, legacyConfig)).toBeNull();
  });

  it("resolves fix_all when needs_clarification and can_fix_all", () => {
    const run = runStub({
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        can_fix_all: true,
        itr_blocking_count: 2,
      },
      journey: {
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "artifact_clarification",
          stage_id: "boundary_detection",
        },
      },
    });
    expect(resolveAutopilotCheckpoint(run, legacyConfig)).toEqual({
      kind: "fix_all",
      stageId: "boundary_detection",
    });
  });

  it("does not resolve write_approval — operator must save manually", () => {
    const run = runStub({
      stages: [{ id: "boundary_detection", title: "Boundaries", status: "awaiting_write_approval", phase: "understand" }],
      job: {
        status: "awaiting_write_approval",
        stage: "boundary_detection",
        pending_write_stage: "boundary_detection",
        pending_write_paths: ["segments/boundaries.json"],
      },
    });
    expect(resolveAutopilotCheckpoint(run, legacyConfig)).toBeNull();
  });

  it("hides review gate only for fix_all autopilot checkpoints", () => {
    const run = runStub({
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        can_fix_all: true,
        itr_blocking_count: 1,
      },
    });
    expect(autopilotHidesReviewGate(run, "boundary_detection", legacyConfig)).toBe(true);
  });

  it("prefers fix_all when ITR issues block save", () => {
    const run = runStub({
      stages: [{ id: "boundary_detection", title: "Boundaries", status: "awaiting_write_approval", phase: "understand" }],
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        pending_write_stage: "boundary_detection",
        pending_write_paths: ["segments/boundaries.json"],
        itr_blocking_count: 5,
        can_fix_all: true,
      },
      journey: {
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "artifact_clarification",
          stage_id: "boundary_detection",
        },
      },
    });
    expect(resolveAutopilotCheckpoint(run, legacyConfig)).toEqual({
      kind: "fix_all",
      stageId: "boundary_detection",
    });
  });

  it("does not auto fix_all when full_autopilot is enabled", () => {
    const run = runStub({
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        can_fix_all: true,
        itr_blocking_count: 2,
      },
      journey: {
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "artifact_clarification",
          stage_id: "boundary_detection",
        },
      },
    });
    expect(resolveAutopilotCheckpoint(run, { journey_ui: { full_autopilot: true } })).toBeNull();
  });

  it("limits write-approval attempts per stage", () => {
    const checkpoint = { kind: "write_approval" as const, stageId: "boundary_detection" };
    expect(canAttemptAutopilotCheckpoint("exec_test", checkpoint)).toBe(true);
    recordAutopilotWriteApprovalAttempt("exec_test", "boundary_detection");
    recordAutopilotWriteApprovalAttempt("exec_test", "boundary_detection");
    recordAutopilotWriteApprovalAttempt("exec_test", "boundary_detection");
    expect(canAttemptAutopilotCheckpoint("exec_test", checkpoint)).toBe(false);
  });

  it("limits fix-all attempts per stage", () => {
    expect(canAttemptAutopilotFixAll("exec_test", "boundary_detection")).toBe(true);
    recordAutopilotFixAllAttempt("exec_test", "boundary_detection");
    recordAutopilotFixAllAttempt("exec_test", "boundary_detection");
    recordAutopilotFixAllAttempt("exec_test", "boundary_detection");
    expect(canAttemptAutopilotFixAll("exec_test", "boundary_detection")).toBe(false);
  });
});
