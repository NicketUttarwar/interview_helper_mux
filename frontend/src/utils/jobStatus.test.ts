import { describe, expect, it } from "vitest";
import type { RunData, StageInfo } from "../types";
import { makeStage } from "../test/runFixtures";
import {
  applyLiveJobToStages,
  isWriteApprovalSaveInProgress,
  isWriteApprovalSaving,
  writeApprovalSaveStageId,
  isJobActivelyRunning,
} from "./jobStatus";

function run(partial: Partial<RunData>): RunData {
  return partial as RunData;
}

describe("isJobActivelyRunning", () => {
  it("treats clarification_pending as in-flight", () => {
    expect(
      isJobActivelyRunning({
        status: "running",
        stage: "boundary_detection",
        clarification_pending: true,
      }),
    ).toBe(true);
  });
});

describe("deprecated write approval helpers", () => {
  it("always report no write-approval save in v2", () => {
    const r = run({
      stages: [
        makeStage("ingest", {
          title: "Ingest",
          status: "awaiting_write_approval",
          phase: "prepare",
        }),
      ],
      job: {
        status: "running",
        mode: "write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
      },
    });
    expect(isWriteApprovalSaving(r.job)).toBe(false);
    expect(isWriteApprovalSaveInProgress(r, { stageId: "ingest" })).toBe(false);
    expect(writeApprovalSaveStageId(r)).toBeNull();
  });
});

describe("applyLiveJobToStages", () => {
  const stages: StageInfo[] = [
    makeStage("edl", { title: "EDL", status: "pending", phase: "create" }),
    makeStage("mix", { title: "Mix", status: "pending", phase: "polish" }),
    makeStage("g1_vo_pickup", {
      title: "G1",
      status: "action_required",
      phase: "create",
    }),
  ];

  it("marks finished stages done from stage_progress without touching gates", () => {
    const next = applyLiveJobToStages(stages, {
      status: "running",
      current_stage: "mix",
      stage_progress: [
        { id: "edl", status: "done" },
        { id: "mix", status: "running" },
      ],
    });
    expect(next.find((s) => s.id === "edl")?.status).toBe("done");
    expect(next.find((s) => s.id === "mix")?.status).toBe("pending");
    expect(next.find((s) => s.id === "g1_vo_pickup")?.status).toBe("action_required");
  });

  it("reopens a done stage when it is the live current_stage", () => {
    const doneMix = [
      makeStage("mix", { title: "Mix", status: "done", phase: "polish" }),
    ];
    const next = applyLiveJobToStages(doneMix, {
      status: "running",
      current_stage: "mix",
    });
    expect(next[0].status).toBe("pending");
  });
});
