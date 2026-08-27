import { describe, expect, it } from "vitest";
import {
  isPartialAutoCheckpoint,
  isPartialAcceleratedRun,
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

  it("hides overlay when partial_auto_complete", () => {
    const r = run({
      meta: {
        run_mode: "partially-accelerated",
        partial_auto_driver_active: false,
        partial_auto_complete: true,
      },
    });
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
  });
});
