import { describe, expect, it } from "vitest";
import type { RunData } from "../types";
import {
  canAutoRunStage,
  isPipelineAutopilotEnabled,
  isPipelineComplete,
  resolveFinalOutputAbsolutePath,
  shouldAutoContinueFromStage,
  shouldAutoNavigateFromStage,
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
    expect(shouldAutoNavigateFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(shouldAutoContinueFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(canAutoRunStage("interview_spine_build")).toBe(true);
    expect(canAutoRunStage("transcript_review")).toBe(false);
  });

  it("blocks auto-continue while handoff review is pending", () => {
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
    });
    expect(shouldAutoNavigateFromStage(run, "speaker_roles", null)).toBe(false);
    expect(shouldAutoContinueFromStage(run, "speaker_roles", null)).toBe(false);
  });

  it("auto-navigates but does not auto-run when next stage has stage_reuse blocking", () => {
    const run = runStub({
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
    expect(shouldAutoNavigateFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(shouldAutoContinueFromStage(run, "source_acoustic_profile", null)).toBe(false);
  });
});
