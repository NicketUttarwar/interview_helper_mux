import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import {
  canLoadPendingWriteContent,
  isStalePendingWriteLoadError,
  resolvePendingWritePaths,
  stageAwaitingWriteApproval,
} from "./writeApproval";
import type { RunData } from "../types";

function runStub(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [],
    ...overrides,
  };
}

describe("resolvePendingWritePaths", () => {
  it("prefers API paths when awaiting approval", () => {
    const run = runStub({
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
      },
    });
    expect(resolvePendingWritePaths(run, "ingest", ["a.json", "b.json"])).toEqual([
      "a.json",
      "b.json",
    ]);
  });

  it("ignores API paths when write approval cleared", () => {
    const run = runStub({
      job: { status: "complete" },
    });
    expect(resolvePendingWritePaths(run, "ingest", ["a.json"])).toEqual([]);
  });

  it("falls back to job pending_write_paths", () => {
    const run = runStub({
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["input/checksum.json"],
      },
    });
    expect(resolvePendingWritePaths(run, "ingest")).toEqual(["input/checksum.json"]);
  });

  it("falls back to run meta pending_write_approval when awaiting", () => {
    const run = runStub({
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
      },
      meta: {
        pending_write_approval: {
          ingest: { paths: ["meta/a.json"] },
        },
      },
    });
    expect(resolvePendingWritePaths(run, "ingest")).toEqual(["meta/a.json"]);
  });
});

describe("stageAwaitingWriteApproval", () => {
  it("matches pending write stage from job", () => {
    const run = runStub({
      job: {
        status: "awaiting_write_approval",
        awaiting_write_approval: true,
        pending_write_stage: "ingest",
      },
    });
    expect(stageAwaitingWriteApproval(run, "ingest")).toBe(true);
    expect(stageAwaitingWriteApproval(run, "transcribe")).toBe(false);
  });

  it("matches stage status when job was cleared after reuse accept", () => {
    const run = runStub({
      stages: [{ id: "ingest", title: "Ingest", status: "awaiting_write_approval", phase: "prepare" }],
      job: { status: "complete" },
    });
    expect(stageAwaitingWriteApproval(run, "ingest")).toBe(true);
    expect(resolvePendingWritePaths(run, "ingest", ["ingest/a.json"])).toEqual(["ingest/a.json"]);
  });

  it("blocks write approval when gui_job is gate for the same stage", () => {
    const run = runStub({
      stages: [
        {
          id: "speaker_roles",
          title: "Speaker roles",
          status: "action_required",
          phase: "understand",
        },
      ],
      job: {
        status: "gate",
        stage: "speaker_roles",
        message: "LLM stage gate (speaker_roles): artifact not complete",
      },
    });
    expect(stageAwaitingWriteApproval(run, "speaker_roles")).toBe(false);
    expect(resolvePendingWritePaths(run, "speaker_roles", ["understanding/analysis_state.json"])).toEqual(
      [],
    );
  });
});

describe("canLoadPendingWriteContent", () => {
  it("returns false when job advanced to a different stage", () => {
    const run = runStub({
      job: {
        status: "complete",
        stage: "transcript_review",
      },
      stages: [
        {
          id: "transcript_review_build",
          title: "STT review prep",
          status: "done",
          phase: "prepare",
        },
      ],
      meta: {
        pending_write_approval: {
          transcript_review_build: { paths: ["transcript/review_queue.json"] },
        },
      },
    });
    expect(canLoadPendingWriteContent(run, "transcript_review_build")).toBe(false);
  });

  it("returns true while awaiting approval with staged paths", () => {
    const run = runStub({
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/normalized.wav"],
      },
    });
    expect(canLoadPendingWriteContent(run, "ingest")).toBe(true);
  });

  it("returns false during write-approval save", () => {
    const run = runStub({
      job: {
        status: "running",
        mode: "write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/normalized.wav"],
      },
    });
    expect(canLoadPendingWriteContent(run, "ingest")).toBe(false);
  });
});

describe("isStalePendingWriteLoadError", () => {
  it("detects flushed staging 404", () => {
    const err = new ApiError(
      "/Users/run/.pending_writes/ingest/ingest/normalized.wav",
      404,
    );
    expect(isStalePendingWriteLoadError(err)).toBe(true);
  });

  it("ignores unrelated 404", () => {
    const err = new ApiError("artifact missing", 404);
    expect(isStalePendingWriteLoadError(err)).toBe(false);
  });
});
