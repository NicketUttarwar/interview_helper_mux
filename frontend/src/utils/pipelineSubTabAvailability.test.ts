import { describe, expect, it } from "vitest";
import { clampPipelineSubTab, pipelineSubTabAvailability } from "./pipelineSubTabAvailability";
import type { RunData, TimelineData } from "../types";

function baseRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [
      { id: "ingest", title: "Ingest", status: "done" },
      { id: "content_context", title: "Content", status: "pending" },
      { id: "segment_classification", title: "Classify", status: "pending" },
      { id: "analysis_profile", title: "Profile", status: "locked" },
    ],
    ...overrides,
  };
}

describe("pipelineSubTabAvailability", () => {
  it("always allows stage and debug tabs", () => {
    const run = baseRun();
    expect(pipelineSubTabAvailability("stage", run, null).available).toBe(true);
    expect(pipelineSubTabAvailability("llm_calls", run, null).available).toBe(true);
  });

  it("locks story until story_board_ready", () => {
    const run = baseRun();
    expect(pipelineSubTabAvailability("story", run, null).available).toBe(false);
    expect(pipelineSubTabAvailability("story", run, null).reason).toContain("content understanding");

    const ready = baseRun({ story_board_ready: true });
    expect(pipelineSubTabAvailability("story", ready, null).available).toBe(true);
  });

  it("locks timeline until segments exist", () => {
    const run = baseRun({ timeline_ready: false });
    const tl: TimelineData = { segments: [], duration_ms: 1 };
    expect(pipelineSubTabAvailability("timeline", run, tl).available).toBe(false);

    const ready = baseRun({ timeline_ready: true });
    expect(pipelineSubTabAvailability("timeline", ready, null).available).toBe(true);
  });

  it("locks profile until ready for review", () => {
    const run = baseRun();
    expect(pipelineSubTabAvailability("profile", run, null).available).toBe(false);
    const ready = baseRun({ profile_ready_for_review: true });
    expect(pipelineSubTabAvailability("profile", ready, null).available).toBe(true);
  });

  it("clamp falls back to stage", () => {
    const run = baseRun();
    expect(clampPipelineSubTab("story", run, null)).toBe("stage");
    expect(clampPipelineSubTab("stage", run, null)).toBe("stage");
  });

  it("flow 2/3 runs use same timeline gating", () => {
    for (const flow of ["flow_2", "flow_3"] as const) {
      const run = baseRun({ selected_flow: flow, timeline_ready: false });
      expect(pipelineSubTabAvailability("timeline", run, null).available).toBe(false);
      const ready = baseRun({ selected_flow: flow, timeline_ready: true });
      expect(pipelineSubTabAvailability("timeline", ready, null).available).toBe(true);
    }
  });
});
