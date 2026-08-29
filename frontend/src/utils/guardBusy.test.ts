import { describe, expect, it, vi } from "vitest";
import { guardBusy } from "./guardBusy";

describe("guardBusy", () => {
  it("blocks when job is running", () => {
    const toast = vi.fn();
    expect(guardBusy(true, false, toast)).toBe(true);
    expect(toast).toHaveBeenCalledWith(
      "A step is already running — watch the activity log.",
      "warning",
    );
  });

  it("blocks when checkpoint is saving", () => {
    const toast = vi.fn();
    expect(guardBusy(false, true, toast)).toBe(true);
    expect(toast).toHaveBeenCalledWith(
      "Checkpoint save in progress — watch Activity (Live).",
      "warning",
    );
  });

  it("allows action when idle", () => {
    const toast = vi.fn();
    expect(guardBusy(false, false, toast)).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });

  it("allows action at partial-auto G0 despite stale job.running", () => {
    const toast = vi.fn();
    const run = {
      transcript_review_pending: true,
      meta: { run_mode: "partially-accelerated" },
    };
    expect(guardBusy(true, false, toast, { run: run as never })).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });

  it("allows action at a G-Framing gate despite stale job.running", () => {
    const toast = vi.fn();
    const run = {
      gap_framing_decision_pending: true,
      meta: { run_mode: "partially-accelerated" },
      job: { status: "gate", message: "Gap framing gate" },
    };
    expect(guardBusy(true, false, toast, { run: run as never })).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });
});
