import { describe, expect, it } from "vitest";
import { buildNumberedStages, resolvePipelineNav, stageNavStatus } from "./pipelineNavigation";
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

describe("stageNavStatus", () => {
  it("marks dismissed audio_preclean as skipped", () => {
    const preclean = stage({ id: "audio_preclean", title: "Audio pre-clean", status: "pending" });
    const run = minimalRun({
      stages: [preclean],
      meta: {
        audio_preclean: {
          decisions: [{ checkpoint: "before_ingest", action: "dismiss" }],
        },
      },
    });
    const numbered = buildNumberedStages(run.stages);
    expect(stageNavStatus(numbered[0], run, null, null)).toBe("skipped");
  });

  it("skipped optional audio_preclean shows skipped nav status", () => {
    const preclean = stage({
      id: "audio_preclean",
      title: "Audio pre-clean",
      status: "done",
      stage_output_mode: "optional_skipped",
      outputs_view: [
        { path: "(skipped)", label: "Skipped", status: "complete", phase: "skipped" },
        { path: "preclean/provider.json", label: "provider", status: "n_a", phase: "n_a" },
      ],
    });
    const run = minimalRun({ stages: [preclean] });
    const numbered = buildNumberedStages(run.stages);
    expect(stageNavStatus(numbered[0], run, null, null)).toBe("skipped");
  });

  it("focusStageId matches resolver stageId for write approval", () => {
    const ingest = stage({ id: "ingest", title: "Ingest", status: "awaiting_write_approval" });
    const run = minimalRun({
      stages: [ingest],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        stage: "ingest",
      },
    });
    const nav = resolvePipelineNav(run, { selectedStageId: "ingest", jobRunning: false });
    const action = resolveOperatorAction(run, { selectedStageId: "ingest", jobRunning: false });
    expect(nav.focusStageId).toBe("ingest");
    expect(action.stageId).toBe("ingest");
  });
});
