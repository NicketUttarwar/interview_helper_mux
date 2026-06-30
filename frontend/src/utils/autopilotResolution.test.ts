import { describe, expect, it, beforeEach } from "vitest";
import type { RunData } from "../types";
import {
  canAttemptAutopilotFixAll,
  clearAutopilotFixAllAttempts,
  recordAutopilotFixAllAttempt,
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

describe("autopilotResolution", () => {
  beforeEach(() => {
    clearAutopilotFixAllAttempts("exec_test", "boundary_detection");
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
    expect(resolveAutopilotCheckpoint(run, null)).toEqual({
      kind: "fix_all",
      stageId: "boundary_detection",
    });
  });

  it("resolves write_approval when staged paths pending", () => {
    const run = runStub({
      stages: [{ id: "boundary_detection", title: "Boundaries", status: "awaiting_write_approval", phase: "understand" }],
      job: {
        status: "awaiting_write_approval",
        stage: "boundary_detection",
        pending_write_stage: "boundary_detection",
        pending_write_paths: ["segments/boundaries.json"],
      },
    });
    expect(resolveAutopilotCheckpoint(run, null)).toEqual({
      kind: "write_approval",
      stageId: "boundary_detection",
    });
  });

  it("hides review gate when autopilot can clear checkpoint", () => {
    const run = runStub({
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        can_fix_all: true,
        itr_blocking_count: 1,
      },
    });
    expect(autopilotHidesReviewGate(run, "boundary_detection", null)).toBe(true);
  });

  it("limits fix-all attempts per stage", () => {
    expect(canAttemptAutopilotFixAll("exec_test", "boundary_detection")).toBe(true);
    recordAutopilotFixAllAttempt("exec_test", "boundary_detection");
    recordAutopilotFixAllAttempt("exec_test", "boundary_detection");
    recordAutopilotFixAllAttempt("exec_test", "boundary_detection");
    expect(canAttemptAutopilotFixAll("exec_test", "boundary_detection")).toBe(false);
  });
});
