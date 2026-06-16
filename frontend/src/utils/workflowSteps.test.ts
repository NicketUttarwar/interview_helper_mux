import { describe, expect, it } from "vitest";
import { workflowStepStatus, stepNeedsCheckpoint } from "./workflowSteps";
import type { RunData } from "../types";

describe("workflowSteps", () => {
  it("returns attention when phase has blocking gate", () => {
    const run: RunData = {
      run_id: "exec_001",
      stages: [
        {
          id: "transcript_review",
          title: "Transcript review",
          description: "",
          status: "action_required",
          operator_phase: "prepare",
        },
      ],
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "Review STT clips",
        blocking: { blocked: true, stage_id: "transcript_review" },
      },
    };
    expect(workflowStepStatus("prepare", run)).toBe("attention");
    expect(stepNeedsCheckpoint("prepare", run)).toBe(true);
  });
});
