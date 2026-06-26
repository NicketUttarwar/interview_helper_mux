import { describe, expect, it } from "vitest";
import {
  isStageReusePending,
  resolveStageReuseCheck,
  stageReuseOffersJobKey,
} from "./stageReuseOffers";
import type { ReuseCandidate, RunData } from "../types";

function candidate(runId: string): ReuseCandidate {
  return {
    run_id: runId,
    source_audio_hash_short: "abc123",
    same_source_audio: true,
    paths: [],
  };
}

function minimalRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_002_test",
    stages: [
      { id: "ingest", title: "Ingest", description: "", status: "done", operator_phase: "prepare" },
      { id: "transcribe", title: "Transcribe", description: "", status: "pending", operator_phase: "prepare" },
    ],
    meta: { source_audio_hash_short: "abc123" },
    ...overrides,
  };
}

describe("stageReuseOffersJobKey", () => {
  it("returns empty when reuse is not pending for this stage", () => {
    expect(
      stageReuseOffersJobKey(
        { needs_stage_reuse: true, stage: "transcribe", reuse_candidates: [candidate("a")] },
        "ingest",
      ),
    ).toBe("");
  });
});

describe("resolveStageReuseCheck", () => {
  it("uses job-embedded candidates when blocking on reuse", () => {
    const run = minimalRun({
      job: {
        status: "needs_operator",
        stage: "transcribe",
        needs_stage_reuse: true,
        reuse_candidates: [candidate("exec_001")],
      },
    });
    const ctx = resolveStageReuseCheck(run, "transcribe", "pending", run.job);
    expect(ctx.enabled).toBe(true);
    expect(ctx.blocking).toBe(true);
    expect(ctx.embeddedCandidates).toHaveLength(1);
  });

  it("uses journey blocking candidates without a separate fetch", () => {
    const run = minimalRun({
      blocking: {
        blocked: true,
        reason: "stage_reuse",
        stage_id: "transcribe",
        reuse_candidates: [candidate("exec_001")],
      },
    });
    const ctx = resolveStageReuseCheck(run, "transcribe", "pending", run.job);
    expect(ctx.enabled).toBe(true);
    expect(ctx.embeddedCandidates[0].run_id).toBe("exec_001");
  });

  it("does not enable reuse UI for unrelated stages", () => {
    const run = minimalRun({
      job: {
        status: "needs_operator",
        stage: "transcribe",
        needs_stage_reuse: true,
        reuse_candidates: [candidate("exec_001")],
      },
    });
    const ctx = resolveStageReuseCheck(run, "ingest", "done", run.job);
    expect(ctx.enabled).toBe(false);
    expect(isStageReusePending(run, "ingest", "done", run.job)).toBe(false);
    expect(isStageReusePending(run, "transcribe", "pending", run.job)).toBe(true);
  });

  it("does not enable reuse UI after operator decided", () => {
    const run = minimalRun({
      meta: { stage_reuse: { audio_preclean: { action: "accept" } } },
      job: {
        needs_stage_reuse: true,
        stage: "audio_preclean",
        reuse_candidates: [candidate("exec_001")],
      },
    });
    const ctx = resolveStageReuseCheck(run, "audio_preclean", "pending", run.job);
    expect(ctx.enabled).toBe(false);
  });
});
