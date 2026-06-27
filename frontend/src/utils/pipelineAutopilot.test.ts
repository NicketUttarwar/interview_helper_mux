import { describe, expect, it } from "vitest";
import type { RunData } from "../types";
import {
  canAutoRunStage,
  isPipelineAutopilotEnabled,
  isPipelineComplete,
  resolveFinalOutputAbsolutePath,
  shouldAutoContinueFromStage,
} from "./pipelineAutopilot";

function runStub(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    working_dir: "/tmp/exec_test",
    stages: [
      { id: "source_acoustic_profile", title: "Source acoustic", status: "done", phase: "understand" },
      { id: "interview_spine_build", title: "Spine", status: "pending", phase: "understand" },
    ],
    journey: { phase: "understand" },
    ...overrides,
  };
}

describe("pipelineAutopilot", () => {
  it("defaults autopilot on unless explicitly disabled", () => {
    expect(isPipelineAutopilotEnabled(null)).toBe(true);
    expect(isPipelineAutopilotEnabled({ journey_ui: { auto_advance_pipeline: false } })).toBe(false);
  });

  it("detects pipeline completion from deliverable", () => {
    const complete = runStub({
      stages: [
        { id: "export", title: "Export", status: "done", phase: "ship" },
      ],
      journey: {
        phase: "ship",
        deliverable: { kind: "master", paths: { master: "flow_1_master/master.wav" } },
      },
    });
    expect(isPipelineComplete(complete)).toBe(true);
  });

  it("builds absolute final output path", () => {
    const run = runStub({
      working_dir: "/Users/me/runs/exec_1/",
      journey: {
        deliverable: { kind: "master", paths: { master: "flow_1_master/master.wav" } },
      },
    });
    expect(resolveFinalOutputAbsolutePath(run)).toBe(
      "/Users/me/runs/exec_1/flow_1_master/master.wav",
    );
  });

  it("auto-continues from a done stage when next is runnable", () => {
    const run = runStub();
    expect(shouldAutoContinueFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(canAutoRunStage("interview_spine_build")).toBe(true);
    expect(canAutoRunStage("transcript_review")).toBe(false);
  });
});
