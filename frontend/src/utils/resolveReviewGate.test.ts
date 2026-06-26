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

  it("returns write_approval when stage awaits save", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [stage("ingest", "awaiting_write_approval")],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/a.json", "ingest/b.wav"],
      },
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toEqual({
      kind: "write_approval",
      pathCount: 2,
    });
  });

  it("returns handoff for done stage without ack", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        {
          ...stage("speaker_roles", "done"),
          handoff_paths: ["understanding/speakers.json"],
        },
      ],
      handoff_ack: {},
    };
    expect(resolveReviewGateSpec(run, run.stages[0], false)).toEqual({
      kind: "handoff",
      pathCount: 1,
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
