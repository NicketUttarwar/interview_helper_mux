import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import {
  isExpectedEmptyApiError,
  reportPanelFetchOutcome,
} from "./safeApi";

describe("safeApi panel fetch policy", () => {
  it("treats 404 as expected empty", () => {
    expect(isExpectedEmptyApiError(new ApiError("not found", 404))).toBe(true);
  });

  it("treats coherence pre-analysis message as expected empty", () => {
    expect(
      isExpectedEmptyApiError(
        new ApiError("Coherence report not found — run analysis on a 30m+ interview first.", 200),
      ),
    ).toBe(true);
  });

  it("does not log expected_empty outcomes", () => {
    const appendClientLog = vi.fn();
    const showToast = vi.fn();
    reportPanelFetchOutcome({
      error: new ApiError("missing", 404),
      kind: "expected_empty",
      label: "Coherence report",
      appendClientLog,
      showToast,
    });
    expect(appendClientLog).not.toHaveBeenCalled();
    expect(showToast).not.toHaveBeenCalled();
  });

  it("logs system failures", () => {
    const appendClientLog = vi.fn();
    reportPanelFetchOutcome({
      error: new ApiError("server blew up", 500),
      kind: "system",
      label: "Coherence report",
      appendClientLog,
    });
    expect(appendClientLog).toHaveBeenCalledWith(
      "Coherence report: server blew up",
      "error",
      undefined,
    );
  });
});
