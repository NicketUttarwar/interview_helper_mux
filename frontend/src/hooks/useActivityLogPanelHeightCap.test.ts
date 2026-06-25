import { describe, expect, it } from "vitest";
import {
  ACTIVITY_LOG_PANEL_HEIGHT_CAP_MULTIPLIER,
  capActivityLogPanelHeight,
} from "./useActivityLogPanelHeightCap";

describe("capActivityLogPanelHeight", () => {
  it("caps at twice the measured base height", () => {
    expect(ACTIVITY_LOG_PANEL_HEIGHT_CAP_MULTIPLIER).toBe(2);
    expect(capActivityLogPanelHeight(240)).toBe(480);
    expect(capActivityLogPanelHeight(317.4)).toBe(635);
  });
});
