import { describe, expect, it } from "vitest";
import {
  firstTodoStepId,
  resolveFocusStepId,
  shouldAdvanceStaleStep,
  substepIdToStepId,
} from "./resolveActiveStep";
import type { RunData } from "../types";

function stage(
  id: string,
  status: RunData["stages"][0]["status"],
  steps: RunData["stages"][0]["guidance"] extends { steps?: infer S } ? S : never,
) {
  return { id, title: id, status, phase: "prepare" as const, guidance: { steps } };
}

describe("substepIdToStepId", () => {
  it("maps known substep prefixes", () => {
    expect(substepIdToStepId("write_approval:ingest")).toBe("write_approval");
    expect(substepIdToStepId("stage_reuse:ingest")).toBe("reuse");
    expect(substepIdToStepId("handoff:speaker_roles")).toBe("handoff");
    expect(substepIdToStepId("run:transcribe")).toBe("run");
  });
});

describe("resolveFocusStepId", () => {
  it("focuses write_approval when stage awaits save", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        stage("ingest", "awaiting_write_approval", [
          { id: "prereqs", status: "done", kind: "info", number: 1, label: "Prereqs", review: [] },
          { id: "run", status: "todo", kind: "run", number: 2, label: "Run", review: [] },
          { id: "write_approval", status: "todo", kind: "write_approval", number: 3, label: "Save", review: [] },
        ]),
      ],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/normalized.wav"],
      },
    };
    expect(resolveFocusStepId(run, "ingest")).toBe("write_approval");
  });

  it("focuses reuse when stage_reuse is blocking", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        stage("transcribe", "pending", [
          { id: "reuse", status: "todo", kind: "reuse", number: 1, label: "Reuse", review: [] },
          { id: "run", status: "waiting", kind: "run", number: 2, label: "Run", review: [] },
        ]),
      ],
      blocking: { blocked: true, reason: "stage_reuse", stage_id: "transcribe" },
    };
    expect(resolveFocusStepId(run, "transcribe")).toBe("reuse");
  });

  it("focuses gate step for action_required stages", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        stage("transcript_review", "action_required", [
          { id: "listen_clips", status: "todo", kind: "gate", number: 1, label: "Listen", review: [] },
          { id: "complete_g0", status: "todo", kind: "gate", number: 4, label: "Complete", review: [] },
        ]),
      ],
    };
    expect(resolveFocusStepId(run, "transcript_review")).toBe("listen_clips");
  });

  it("focuses active run step while job is running", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        stage("transcribe", "pending", [
          { id: "run", status: "active", kind: "run", number: 1, label: "Run", review: [] },
        ]),
      ],
      job: { status: "running", stage: "transcribe", current_stage: "transcribe" },
    };
    expect(resolveFocusStepId(run, "transcribe")).toBe("run");
  });
});

describe("shouldAdvanceStaleStep", () => {
  it("advances when current step is done", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        stage("audio_preclean", "awaiting_write_approval", [
          { id: "review_offer", status: "done", kind: "preclean", number: 1, label: "Offer", review: [] },
          { id: "wait_run", status: "done", kind: "run", number: 2, label: "Wait", review: [] },
          { id: "write_approval", status: "todo", kind: "write_approval", number: 3, label: "Save", review: [] },
        ]),
      ],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "audio_preclean",
        pending_write_paths: ["preclean/isolated.wav"],
      },
    };
    expect(shouldAdvanceStaleStep(run, "audio_preclean", "review_offer")).toBe("write_approval");
  });
});

describe("firstTodoStepId", () => {
  it("skips done steps", () => {
    const run: RunData = {
      run_id: "exec_test",
      stages: [
        stage("ingest", "pending", [
          { id: "prereqs", status: "done", kind: "info", number: 1, label: "Prereqs", review: [] },
          { id: "run", status: "todo", kind: "run", number: 2, label: "Run", review: [] },
        ]),
      ],
    };
    expect(firstTodoStepId(run, "ingest")).toBe("run");
  });
});
