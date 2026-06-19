import { describe, expect, it } from "vitest";
import { findPendingFocusStage } from "./checkpoint";
import type { RunData } from "../types";

function minimalRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [],
    ...overrides,
  };
}

describe("findPendingFocusStage", () => {
  it("returns transcribe when journey blocking reason is stage_reuse", () => {
    const run = minimalRun({
      stages: [
        {
          id: "ingest",
          title: "Ingest",
          description: "",
          status: "done",
        },
        {
          id: "transcribe",
          title: "Transcribe",
          description: "",
          status: "pending",
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
          message: "Transcribe can reuse outputs from exec_000.",
        },
      },
    });
    expect(findPendingFocusStage(run)).toBe("transcribe");
  });
});
