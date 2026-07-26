import { describe, expect, it } from "vitest";
import type { RunData } from "../types";
import { makeJourney, makeStage } from "../test/runFixtures";
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
      makeStage("source_acoustic_profile", {
        title: "Source acoustic",
        status: "done",
        phase: "understand",
      }),
      makeStage("interview_spine_build", { title: "Spine", status: "pending", phase: "understand" }),
    ],
    journey: makeJourney({ phase: "understand" }),
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
        makeStage("export", { title: "Export", status: "done", phase: "ship" }),
      ],
      journey: makeJourney({
        phase: "ship",
        deliverable: { kind: "master", paths: { master: "master/master.wav" } },
      }),
    });
    expect(isPipelineComplete(complete)).toBe(true);
  });

  it("builds absolute final output path", () => {
    const run = runStub({
      working_dir: "/Users/me/runs/exec_1/",
      journey: makeJourney({
        deliverable: { kind: "master", paths: { master: "master/master.wav" } },
      }),
    });
    expect(resolveFinalOutputAbsolutePath(run)).toBe(
      "/Users/me/runs/exec_1/master/master.wav",
    );
  });

  it("auto-continues from a done stage when next is runnable", () => {
    const run = runStub();
    expect(shouldAutoNavigateFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(shouldAutoContinueFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(canAutoRunStage("interview_spine_build")).toBe(true);
    expect(canAutoRunStage("transcript_review")).toBe(false);
  });

  it("does not block auto-continue when handoffs disabled (v2)", () => {
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
    });
    expect(shouldAutoNavigateFromStage(run, "speaker_roles", null)).toBe(true);
    expect(shouldAutoContinueFromStage(run, "speaker_roles", null)).toBe(true);
  });

  it("auto-navigates but does not auto-run when next stage has stage_reuse blocking", () => {
    const run = runStub({
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
    expect(shouldAutoNavigateFromStage(run, "source_acoustic_profile", null)).toBe(true);
    expect(shouldAutoContinueFromStage(run, "source_acoustic_profile", null)).toBe(false);
  });
});
