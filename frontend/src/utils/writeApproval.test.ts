import { describe, expect, it } from "vitest";
import { resolvePendingWritePaths, stageAwaitingWriteApproval } from "./writeApproval";
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
});
