import { describe, expect, it } from "vitest";
import {
  deliveryOrderViolation,
  isPartialAutoCheckpoint,
  isPartialAcceleratedRun,
  isTranscriptReviewCheckpoint,
  shouldShowAcceleratedRunOverlay,
} from "./partialAcceleratedGuard";
import type { RunData } from "../types";

function run(partial: Partial<RunData>): RunData {
  return partial as RunData;
}

describe("partialAcceleratedGuard", () => {
  it("detects partially-accelerated runs", () => {
    expect(isPartialAcceleratedRun(run({ meta: { run_mode: "partially-accelerated" } }))).toBe(true);
    expect(isPartialAcceleratedRun(run({ meta: { partial_auto: true } }))).toBe(true);
    expect(isPartialAcceleratedRun(run({ meta: { run_mode: "manual" } }))).toBe(false);
  });

  it("lifts overlay at transcript_review blocking", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true },
      journey: { blocking: { blocked: true, reason: "transcript_review", stage_id: "transcript_review" } },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
  });

  it("lifts overlay when transcript_review_pending is set", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true },
      transcript_review_pending: true,
    });
    expect(isTranscriptReviewCheckpoint(r)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
  });

  it("lifts overlay for gate job with transcript review message and no stage", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true },
      job: {
        status: "gate",
        message: "Analysis paused for transcript review. Correct STT in the GUI.",
      },
    });
    expect(isTranscriptReviewCheckpoint(r)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
  });

  it("hides overlay while peeking at logs", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true },
      journey: { blocking: { blocked: false } },
    });
    expect(shouldShowAcceleratedRunOverlay(r, { pending: false }, { peeking: true })).toBe(false);
  });

  it("lifts overlay at g-publish when package ready", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true },
    });
    const gPublish = { pending: true, package_ready: true, skipped: false };
    expect(isPartialAutoCheckpoint(r, gPublish)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, gPublish)).toBe(false);
  });

  it("shows overlay during automated phase", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true },
      journey: { blocking: { blocked: false } },
    });
    expect(shouldShowAcceleratedRunOverlay(r, { pending: false })).toBe(true);
  });

  it("detects 5C delivery order violations", () => {
    expect(deliveryOrderViolation("vo_synthesize", "vo_line_adjudicate")).toBe(true);
    expect(deliveryOrderViolation("edl_narrative_audit", "vo_synthesize")).toBe(true);
    expect(deliveryOrderViolation("vo_line_adjudicate", "vo_synthesize")).toBe(false);
  });
});
