import { describe, expect, it } from "vitest";
import { buildPhaseSubsteps, isPhaseFullyComplete } from "./phaseSubsteps";
import type { RunData, StageInfo } from "../types";

function stage(partial: Partial<StageInfo> & { id: string }): StageInfo {
  return {
    title: partial.id,
    description: "",
    status: "pending",
    operator_phase: "prepare",
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

describe("phaseSubsteps", () => {
  it("aggregates todo substeps capped at 5", () => {
    const stages = Array.from({ length: 8 }, (_, i) =>
      stage({
        id: `stage_${i}`,
        status: "action_required",
        operator_phase: "prepare",
        guidance: {
          phase_label: "Prepare",
          prerequisites: [],
          actions: [{ id: `a${i}`, label: `Action ${i}`, status: "todo" }],
          unlocks: "",
        },
      }),
    );
    const run = minimalRun({
      stages,
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "Go",
        blocking: { blocked: false },
        phase_progress: { prepare: { done: 0, total: 8 } },
      },
    });
    const summary = buildPhaseSubsteps(run, "prepare");
    expect(summary.todoSubsteps.length).toBeLessThanOrEqual(5);
    expect(summary.stagesTotal).toBe(8);
  });

  it("detects phase fully complete", () => {
    const run = minimalRun({
      stages: [
        stage({ id: "ingest", status: "done" }),
        stage({ id: "transcribe", status: "done" }),
      ],
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "Next",
        blocking: { blocked: false },
      },
    });
    expect(isPhaseFullyComplete(run, "prepare")).toBe(true);
  });
});
