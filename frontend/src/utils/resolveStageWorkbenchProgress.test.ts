import { describe, expect, it } from "vitest";
import type { RunData, StageInfo } from "../types";
import {
  findActionableWorkbenchSteps,
  resolveStageWorkbenchProgress,
} from "./resolveStageWorkbenchProgress";

function stage(overrides: Partial<StageInfo> = {}): StageInfo {
  return {
    id: "disfluency_review",
    title: "Disfluency review",
    status: "action_required",
    phase: "gate",
    guidance: {
      steps: [
        {
          id: "review_fillers",
          number: 1,
          label: "Review filler clips",
          status: "todo",
          kind: "gate",
          primary_button: "Confirm all & continue",
          review: [],
        },
        {
          id: "complete_g05",
          number: 3,
          label: "Sign-off",
          status: "todo",
          kind: "gate",
          primary_button: "Continue pipeline",
          secondary_button: "Confirm all & continue",
          review: [],
        },
      ],
    },
    ...overrides,
  } as StageInfo;
}

describe("resolveStageWorkbenchProgress", () => {
  it("finds actionable substeps with primary buttons", () => {
    const s = stage();
    const steps = findActionableWorkbenchSteps(s, { run_id: "exec_test", stages: [s] } as RunData);
    expect(steps.map((x) => x.id)).toEqual(["review_fillers", "complete_g05"]);
  });

  it("returns review gate spec for disfluency action_required", () => {
    const s = stage();
    const run = { run_id: "exec_test", stages: [s] } as RunData;
    const progress = resolveStageWorkbenchProgress(run, s, false, null);
    expect(progress?.reviewGateSpec?.kind).toBe("disfluency_review");
  });
});
