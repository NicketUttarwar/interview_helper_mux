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

  it("returns g1_vo for pickup gate when operator must act", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("g1_vo_pickup", "action_required")],
      g1_missing: ["line-1"],
      g1_clear: false,
      operator_gates: {
        g1_vo_pickup: { operator_must_act: true, open: true },
      },
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toEqual({
      kind: "g1_vo",
      missingCount: 1,
    });
  });

  it("returns null for automation_pending G1", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("g1_vo_pickup", "automation_pending")],
      g1_missing: ["line-1"],
      g1_clear: true,
      operator_gates: {
        g1_vo_pickup: {
          operator_must_act: false,
          severity: "automation_pending",
          open: true,
        },
      },
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toBeNull();
  });

  it("returns null when showDoneShell is true", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("transcript_review", "action_required")],
    };
    expect(resolveReviewGateSpec(run, run.stages[0], true)).toBeNull();
  });

  it("returns transcript_review when job status is gate at G0", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("transcript_review", "action_required")],
      job: {
        status: "gate",
        stage: "transcript_review",
        message: "Transcript review required.",
      },
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toEqual({
      kind: "transcript_review",
    });
  });
});
