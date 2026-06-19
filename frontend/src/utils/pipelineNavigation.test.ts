import { describe, expect, it } from "vitest";
import { buildNumberedStages, stageNavStatus } from "./pipelineNavigation";
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
});
