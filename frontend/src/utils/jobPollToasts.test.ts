import { describe, expect, it } from "vitest";
import { shouldSuppressJobPollTerminalToast } from "./jobPollToasts";

describe("shouldSuppressJobPollTerminalToast", () => {
  it("suppresses stale terminal job when poll never saw running", () => {
    expect(
      shouldSuppressJobPollTerminalToast(false, {
        status: "error",
        message: "Old failure",
      }),
    ).toBe(true);
  });

  it("allows terminal toast after poll observed running", () => {
    expect(
      shouldSuppressJobPollTerminalToast(true, {
        status: "error",
        message: "Step failed",
      }),
    ).toBe(false);
  });
});
