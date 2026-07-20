import { describe, expect, it } from "vitest";
import { resolveReviewGateSpec } from "./resolveReviewGate";
import type { RunData } from "../types";

function stage(
  id: string,
  status: RunData["stages"][0]["status"],
  steps?: RunData["stages"][0]["guidance"] extends { steps?: infer S } ? S : never,
) {
  return { id, title: id, status, phase: "prepare" as const, guidance: { steps } };
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
