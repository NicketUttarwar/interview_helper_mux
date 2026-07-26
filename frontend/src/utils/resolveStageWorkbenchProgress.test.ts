import { describe, expect, it } from "vitest";
import type { RunData, StageInfo } from "../types";
import { makeGuidance, makeStage, makeStep } from "../test/runFixtures";
import {
  findActionableWorkbenchSteps,
  resolveStageWorkbenchProgress,
} from "./resolveStageWorkbenchProgress";

function stage(overrides: Partial<StageInfo> = {}): StageInfo {
  return makeStage("disfluency_review", {
    title: "Disfluency review",
    status: "action_required",
    phase: "gate",
    guidance: makeGuidance({
      steps: [
        makeStep("review_fillers", {
          number: 1,
          label: "Review filler clips",
          kind: "gate",
          primary_button: "Confirm all & continue",
        }),
        makeStep("complete_g05", {
          number: 3,
          label: "Sign-off",
          kind: "gate",
          primary_button: "Continue pipeline",
          secondary_button: "Confirm all & continue",
        }),
      ],
    }),
    ...overrides,
  });
}

describe("resolveStageWorkbenchProgress", () => {
  it("finds actionable substeps with primary buttons", () => {
    const s = stage();
    const steps = findActionableWorkbenchSteps(s, { run_id: "exec_test", stages: [s] } as RunData);
    expect(steps.map((x) => x.id)).toEqual(["review_fillers", "complete_g05"]);
  });

  it("returns no review gate spec or attention for removed disfluency_review stage", () => {
    const s = stage();
    const run = { run_id: "exec_test", stages: [s] } as RunData;
    const progress = resolveStageWorkbenchProgress(run, s, false, null);
    expect(progress?.reviewGateSpec).toBeNull();
    // No attention item is enqueued for the removed stage, so the banner falls
    // back to the substep's own button rather than a gate checkpoint label.
    expect(progress?.attentionLabel).toBe("Confirm all & continue");
  });

  it("prioritizes artifact clarification before write approval when ITR blocks", () => {
    const s = stage({
      id: "boundary_detection",
      title: "Segment boundaries",
      status: "awaiting_write_approval",
      guidance: makeGuidance({
        steps: [
          makeStep("artifact_clarification", {
            number: 1,
            label: "Resolve artifact issues",
            kind: "artifact_clarification",
            primary_button: "Fix issues",
          }),
          makeStep("write_approval", {
            number: 2,
            label: "Review staged files",
            kind: "write_approval",
            primary_button: "Save",
          }),
        ],
      }),
    });
    const run = {
      run_id: "exec_test",
      stages: [s],
      job: {
        status: "needs_clarification",
        stage: "boundary_detection",
        itr_blocking_count: 2,
        awaiting_write_approval: true,
      },
    } as RunData;
    const steps = findActionableWorkbenchSteps(s, run);
    expect(steps[0]?.id).toBe("artifact_clarification");
  });
});
