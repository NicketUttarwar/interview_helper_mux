import { describe, expect, it } from "vitest";
import { resolveReviewGateSpec } from "./resolveReviewGate";
import type { RunData, StageInfo, StageStep } from "../types";
import { makeGuidance, makeStage } from "../test/runFixtures";

function stage(id: string, status: StageInfo["status"], steps?: StageStep[]): StageInfo {
  return makeStage(id, { status, phase: "prepare", guidance: makeGuidance({ steps }) });
}

describe("resolveReviewGateSpec", () => {
  it("returns transcript_review for G0 action_required", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("transcript_review", "action_required")],
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toEqual({
      kind: "transcript_review",
    });
  });

  it("returns g1_vo for pickup gate", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("g1_vo_pickup", "action_required")],
      g1_missing: ["line-1"],
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toEqual({
      kind: "g1_vo",
      missingCount: 1,
    });
  });

  it("returns null when showDoneShell is true", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("transcript_review", "action_required")],
    };
    expect(resolveReviewGateSpec(run, run.stages[0], true)).toBeNull();
  });
});
