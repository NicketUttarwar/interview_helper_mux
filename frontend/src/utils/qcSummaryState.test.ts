import { describe, expect, it } from "vitest";
import { resolveQcBlocksShip, resolveQcDisplayState } from "./qcSummaryState";
import { WIRE_STATUS_ADVISORY_FAIL, WIRE_STATUS_PASS } from "./qualityStatus";

describe("qcSummaryState G-02", () => {
  it("maps pass / advisory_fail / blocking_fail / waived", () => {
    expect(resolveQcDisplayState({ passed: true })).toBe(WIRE_STATUS_PASS);
    expect(resolveQcDisplayState({ passed: false, advisory: true })).toBe(
      WIRE_STATUS_ADVISORY_FAIL,
    );
    expect(resolveQcDisplayState({ passed: false, blocking: true })).toBe("blocking_fail");
    expect(resolveQcDisplayState({ passed: false, status: "waived_unattended" })).toBe("waived");
  });

  it("blocksShip from publish_allowed false, not only summary.blocking", () => {
    expect(
      resolveQcBlocksShip(
        { passed: false, blocking: false, publish_allowed: false },
        "post_master_quality",
      ),
    ).toBe(true);
    expect(
      resolveQcBlocksShip(
        { passed: false, blocking: true },
        "listen_delight",
        { post_master_quality: { publish_allowed: false } },
      ),
    ).toBe(true);
    expect(
      resolveQcBlocksShip(
        { passed: false, blocking: true, advisory: true },
        "listen_delight",
        { post_master_quality: { publish_allowed: true } },
      ),
    ).toBe(false);
  });
});
