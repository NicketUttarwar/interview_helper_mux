import { describe, expect, it } from "vitest";
import type { RunData } from "../types";
import { resolveOperatorCover } from "./partialAcceleratedGuard";

function partialAutoRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    meta: {
      run_mode: "partially-accelerated",
      partial_auto: true,
      partial_auto_driver_active: true,
    },
    transcript_review_pending: false,
    stages: [],
    ...overrides,
  } as RunData;
}

describe("partialAutoG0Flow", () => {
  it("shows accelerated cover after G0 complete while driver is active", () => {
    const run = partialAutoRun();
    expect(resolveOperatorCover(run, null, { jobRunning: false })).toBe("accelerated");
  });

  it("lifts cover during transcript review checkpoint", () => {
    const run = partialAutoRun({ transcript_review_pending: true });
    expect(resolveOperatorCover(run, null, { jobRunning: true })).toBe("none");
  });
});
