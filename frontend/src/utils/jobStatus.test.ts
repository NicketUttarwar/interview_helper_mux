import { describe, expect, it } from "vitest";
import type { RunData } from "../types";
import {
  isWriteApprovalSaveInProgress,
  isWriteApprovalSaving,
  writeApprovalSaveStageId,
} from "./jobStatus";

function run(partial: Partial<RunData>): RunData {
  return partial as RunData;
}

describe("isWriteApprovalSaveInProgress", () => {
  it("detects server write_approval job for matching stage", () => {
    const r = run({
      stages: [{ id: "ingest", title: "Ingest", status: "awaiting_write_approval", phase: "prepare" }],
      job: {
        status: "running",
        mode: "write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
      },
    });
    expect(isWriteApprovalSaving(r.job)).toBe(true);
    expect(isWriteApprovalSaveInProgress(r, { stageId: "ingest" })).toBe(true);
    expect(isWriteApprovalSaveInProgress(r, { stageId: "audio_preclean" })).toBe(false);
  });

  it("detects client actionBusy while stage awaits write approval", () => {
    const r = run({
      stages: [
        { id: "audio_preclean", title: "Pre-clean", status: "awaiting_write_approval", phase: "prepare" },
      ],
      job: { status: "awaiting_write_approval", stage: "audio_preclean", pending_write_stage: "audio_preclean" },
    });
    expect(isWriteApprovalSaveInProgress(r, { actionBusy: true, stageId: "audio_preclean" })).toBe(true);
    expect(isWriteApprovalSaveInProgress(r, { actionBusy: false, stageId: "audio_preclean" })).toBe(false);
  });
});

describe("writeApprovalSaveStageId", () => {
  it("returns stage id during write_approval save", () => {
    const r = run({
      job: { status: "running", mode: "write_approval", pending_write_stage: "ingest" },
    });
    expect(writeApprovalSaveStageId(r)).toBe("ingest");
  });
});
