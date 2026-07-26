import { describe, expect, it } from "vitest";
import type { RunData, StageInfo } from "../types";
import { listAttentionItems } from "./attentionQueue";

function stage(id: string, status: StageInfo["status"]): StageInfo {
  return { id, title: id, description: "", status, operator_phase: "prepare" };
}

describe("attentionQueue", () => {
  it("omits write_approval when job is running", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("ingest", "awaiting_write_approval")],
      job: {
        status: "running",
        stage: "ingest",
        current_stage: "ingest",
        pending_write_stage: "ingest",
        awaiting_write_approval: true,
        message: "Hashing",
      },
    };
    const items = listAttentionItems(run);
    expect(items.some((i) => i.kind === "write_approval")).toBe(false);
  });

  it("omits write_approval when job idle and awaiting (v2 auto-commit)", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("ingest", "awaiting_write_approval")],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
        message: "2 files",
      },
    };
    const items = listAttentionItems(run);
    expect(items.some((i) => i.kind === "write_approval")).toBe(false);
  });

  it.each(["analysis_profile", "disfluency_extract", "disfluency_review"])(
    "ignores removed pre-v2 stage %s in old run payloads",
    (stageId) => {
      const run: RunData = {
        run_id: "exec_test",
        stages: [stage(stageId, "action_required")],
        job: { status: "gate", stage: stageId, message: "Review required" },
        journey: {
          phase: "understand",
          milestones: {},
          next_action: "x",
          blocking: { blocked: true, stage_id: stageId, reason: "llm_gate" },
        } as RunData["journey"],
        profile_gate_pending: true,
        profile_verified: false,
      };
      expect(listAttentionItems(run)).toEqual([]);
    },
  );
});
