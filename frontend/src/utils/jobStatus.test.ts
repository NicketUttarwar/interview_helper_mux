import { describe, expect, it } from "vitest";
import type { RunData } from "../types";
import {
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
      stages: [{ id: "ingest", title: "Ingest", status: "awaiting_write_approval", phase: "prepare" }],
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
