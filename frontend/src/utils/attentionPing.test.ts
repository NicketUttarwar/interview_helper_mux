import { describe, expect, it } from "vitest";
import {
  maybePingForRequiredAttention,
  playAttentionPing,
  requiredAttentionKey,
} from "./attentionPing";
import type { RunData, StageInfo } from "../types";

function stage(id: string, status: StageInfo["status"], title = id): StageInfo {
  return { id, title, status, description: `${title} step` };
}

function baseRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [],
    journey: { phase: "prepare", milestones: {}, next_action: "Continue" },
    ...overrides,
  } as RunData;
}

describe("requiredAttentionKey", () => {
  it("is empty when no attention is required", () => {
    expect(requiredAttentionKey(baseRun())).toBe("");
  });

  it("includes write approval gates", () => {
    const run = baseRun({
      stages: [stage("ingest", "awaiting_write_approval")],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
      },
    });
    expect(requiredAttentionKey(run)).toContain("write_approval:ingest");
  });

  it("includes checkpoint gates", () => {
    const run = baseRun({
      stages: [stage("transcript_review", "action_required")],
      job: { status: "gate", stage: "transcript_review" },
    });
    expect(requiredAttentionKey(run)).toContain("gate:transcript_review");
  });
});

describe("maybePingForRequiredAttention", () => {
  it("pings once per distinct attention state", () => {
    const lastKey = { current: "" };
    const run = baseRun({
      stages: [stage("transcript_review", "action_required")],
      job: { status: "gate", stage: "transcript_review" },
    });

    expect(maybePingForRequiredAttention(run, false, lastKey)).toBe(true);
    expect(maybePingForRequiredAttention(run, false, lastKey)).toBe(false);
    expect(lastKey.current).toContain("gate:transcript_review");
  });

  it("records key but skips audio when muted", () => {
    const lastKey = { current: "" };
    const run = baseRun({
      stages: [stage("transcript_review", "action_required")],
      job: { status: "gate", stage: "transcript_review" },
    });
    expect(maybePingForRequiredAttention(run, true, lastKey)).toBe(true);
    expect(lastKey.current).not.toBe("");
  });

  it("resets key when attention clears", () => {
    const lastKey = { current: "gate:transcript_review" };
    expect(maybePingForRequiredAttention(baseRun(), false, lastKey)).toBe(false);
    expect(lastKey.current).toBe("");
  });
});

describe("playAttentionPing", () => {
  it("no-ops when muted", () => {
    expect(() => playAttentionPing(true)).not.toThrow();
  });
});
