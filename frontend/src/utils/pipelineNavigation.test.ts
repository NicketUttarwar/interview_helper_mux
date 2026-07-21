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

describe("buildNumberedStages", () => {
  it("hidden gap-fill stages excluded from numbering", () => {
    const visible = stage({ id: "ingest", title: "Ingest", status: "done" });
    const hidden = stage({
      id: "missing_framing",
      title: "Missing framing",
      status: "done",
      stage_visibility: "hidden",
    });
    const run = minimalRun({ stages: [visible, hidden] });
    const numbered = buildNumberedStages(run.stages);
    expect(numbered).toHaveLength(1);
    expect(numbered[0].stage.id).toBe("ingest");
    expect(numbered[0].number).toBe(1);
  });
});

describe("stageNavStatus", () => {
  it("marks dismissed audio_preclean as done (collapsed complete section)", () => {
    const preclean = stage({ id: "audio_preclean", title: "Audio pre-clean", status: "done" });
    const run = minimalRun({
      stages: [preclean],
      meta: {
        audio_preclean: {
          decisions: [{ checkpoint: "before_ingest", action: "dismiss" }],
        },
      },
    });
    const numbered = buildNumberedStages(run.stages);
    expect(stageNavStatus(numbered[0], run, null, null)).toBe("done");
  });

  it("optional_skipped audio_preclean shows done nav status", () => {
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
    expect(stageNavStatus(numbered[0], run, null, null)).toBe("done");
  });

  it("does not focus write approval in v2 (auto_commit_artifacts)", () => {
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
    expect(nav.focusStageId).toBeNull();
    expect(action.stageId).toBeNull();
    expect(action.mode).toBe("idle");
  });
});
