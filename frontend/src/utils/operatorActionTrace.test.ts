import { describe, expect, it } from "vitest";
import {
  formatClientTraceDump,
  getClientTraceBuffer,
  pushClientTrace,
} from "./operatorActionTrace";

describe("operatorActionTrace", () => {
  it("pushes and formats dump", () => {
    pushClientTrace({
      action_id: "gui.write_approval.save",
      message: "Saving files",
      level: "action",
    });
    const buf = getClientTraceBuffer();
    expect(buf.length).toBeGreaterThan(0);
    const text = formatClientTraceDump();
    expect(text).toContain("gui.write_approval.save");
  });

  it("dedupes info within 5s by action_id", () => {
    const before = getClientTraceBuffer().length;
    pushClientTrace({ action_id: "gui.nav.tab", message: "a", level: "info" });
    pushClientTrace({ action_id: "gui.nav.tab", message: "b", level: "info" });
    expect(getClientTraceBuffer().length).toBe(before + 1);
  });
});
