import { describe, expect, it } from "vitest";
import { findPendingFocusStage } from "./checkpoint";
import { resolveOperatorAction } from "./resolveOperatorAction";
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

  it("aligns with resolver.stageId for write approval", () => {
    const run = minimalRun({
      stages: [
        {
          id: "ingest",
          title: "Ingest",
          description: "",
          status: "awaiting_write_approval",
        },
      ],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/normalized.wav"],
      },
    });
    const focus = findPendingFocusStage(run);
    const action = resolveOperatorAction(run);
    expect(focus).toBe("ingest");
    expect(action.stageId).toBe("ingest");
    expect(action.mode).toBe("needs_you");
  });

  it("prefers transcript review gate before later pending automated stages", () => {
    const run = minimalRun({
      stages: [
        { id: "ingest", title: "Ingest", description: "", status: "done", phase: "analysis" },
        { id: "transcribe", title: "Transcribe", description: "", status: "done", phase: "analysis" },
        {
          id: "transcript_review_build",
          title: "STT review prep",
          description: "",
          status: "done",
          phase: "analysis",
        },
        {
          id: "transcript_review",
          title: "Transcript review",
          description: "",
          status: "action_required",
          phase: "gate",
        },
        {
          id: "disfluency_extract",
          title: "Disfluency extract",
          description: "",
          status: "locked",
          phase: "analysis",
        },
      ],
      job: { status: "complete" },
    });
    expect(findPendingFocusStage(run)).toBe("transcript_review");
    expect(resolveOperatorAction(run).stageId).toBe("transcript_review");
  });
});
