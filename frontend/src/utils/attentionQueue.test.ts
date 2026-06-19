import { describe, expect, it } from "vitest";
import {
  countRequiredAttention,
  listRequiredAttentionItems,
  phaseAttentionStatus,
} from "./attentionQueue";
import type { RunData } from "../types";

function minimalRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [],
    ...overrides,
  };
}

describe("attentionQueue", () => {
  it("prioritizes action_required gate over blocking", () => {
    const run = minimalRun({
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
        blocking: { blocked: false },
      },
    });
    const items = listRequiredAttentionItems(run);
    expect(items[0]?.kind).toBe("gate");
    expect(items[0]?.stageId).toBe("transcript_review");
  });

  it("marks phase with attention status", () => {
    const run = minimalRun({
      stages: [
        {
          id: "g2_flow_select",
          title: "Choose output",
          description: "",
          status: "action_required",
          operator_phase: "complete",
        },
      ],
      journey: {
        phase: "complete",
        milestones: {},
        next_action: "Confirm output type",
        blocking: { blocked: true, stage_id: "g2_flow_select", message: "Confirm output type" },
      },
    });
    expect(phaseAttentionStatus("complete", run)).toBe("attention");
    expect(countRequiredAttention(run)).toBeGreaterThan(0);
  });

  it("maps journey stage_reuse blocking to stage_reuse item", () => {
    const run = minimalRun({
      stages: [
        {
          id: "transcribe",
          title: "Transcribe",
          description: "",
          status: "pending",
          operator_phase: "prepare",
        },
      ],
      job: { status: "complete" },
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "Choose reuse",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "transcribe",
          message: "Transcribe can reuse outputs from exec_001.",
        },
      },
    });
    const items = listRequiredAttentionItems(run);
    expect(items.some((i) => i.kind === "stage_reuse" && i.stageId === "transcribe")).toBe(
      true,
    );
    expect(items.some((i) => i.title === "Pipeline blocked")).toBe(false);
  });
});
