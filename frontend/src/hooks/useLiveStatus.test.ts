import { describe, expect, it } from "vitest";
import { deriveLiveStatusCopy } from "./useLiveStatus";
import type { RunData } from "../types";

function minimalRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [
      {
        id: "ingest",
        title: "Ingest",
        description: "",
        status: "awaiting_write_approval",
        operator_phase: "prepare",
      },
    ],
    ...overrides,
  };
}

describe("deriveLiveStatusCopy", () => {
  it("uses resolver subline when write approval is pending", () => {
    const run = minimalRun({
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
        message: "Save 2 files",
      },
    });
    const copy = deriveLiveStatusCopy({
      run,
      jobRunning: false,
      selectedStageId: "ingest",
      logEntries: [],
      apiGrants: {},
      cmd: { kind: "blocked", statusLine: "Blocked", primaryLabel: null, onPrimary: null },
    });
    expect(copy.subline).toContain("save");
    expect(copy.activityKind).toBe("blocked");
  });

  it("shows resolver running headline when job is active", () => {
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
      job: {
        status: "running",
        stage: "transcribe",
        current_stage: "transcribe",
        stage_index: 3,
        stage_total: 8,
        message: "Transcribing audio…",
      },
    });
    const copy = deriveLiveStatusCopy({
      run,
      jobRunning: true,
      selectedStageId: "transcribe",
      logEntries: [],
      apiGrants: {},
      cmd: { kind: "running", statusLine: "Running", primaryLabel: null, onPrimary: null },
    });
    expect(copy.activityKind).toBe("running");
    expect(copy.headline).toContain("Running Transcribe");
    expect(copy.headline).toContain("Transcribing");
  });
});
