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
      "Saving checkpoint — wait a moment, then try again.",
      "warning",
    );
  });

  it("allows action when idle", () => {
    const toast = vi.fn();
    expect(guardBusy(false, false, toast)).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });
});
