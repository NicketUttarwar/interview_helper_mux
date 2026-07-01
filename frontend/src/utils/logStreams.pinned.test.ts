import { describe, expect, it } from "vitest";
import type { LogEntry } from "../types";
import { selectPinnedAlerts } from "./logStreams";

function entry(ts: string, level: LogEntry["level"], message: string, stage?: string): LogEntry {
  return { ts, level, message, stage };
}

describe("selectPinnedAlerts", () => {
  const errors = [
    entry("2026-01-01T00:00:01Z", "error", "Error one", "boundary_detection"),
    entry("2026-01-01T00:00:02Z", "error", "Error two", "boundary_detection"),
    entry("2026-01-01T00:00:03Z", "error", "Error three", "boundary_detection"),
  ];
  const warnings = [
    entry("2026-01-01T00:00:04Z", "warning", "Warn one", "boundary_detection"),
    entry("2026-01-01T00:00:05Z", "warning", "Warn two", "boundary_detection"),
  ];

  it("returns latest error as primary when collapsed", () => {
    const all = [...errors, ...warnings];
    const sel = selectPinnedAlerts(all, { expanded: false });
    expect(sel.primaryError?.message).toBe("Error three");
    expect(sel.errorOverflow).toBe(2);
    expect(sel.warningOverflow).toBe(2);
    expect(sel.allPinned).toHaveLength(5);
  });

  it("limits displayed entries when expanded", () => {
    const all = [...errors, ...warnings];
    const sel = selectPinnedAlerts(all, { expanded: true });
    expect(sel.displayedErrors).toHaveLength(2);
    expect(sel.displayedWarnings).toHaveLength(1);
    expect(sel.errorOverflow).toBe(1);
    expect(sel.warningOverflow).toBe(1);
  });

  it("filters by stage", () => {
    const mixed = [
      ...errors,
      entry("2026-01-01T00:00:06Z", "error", "Other stage", "ingest"),
    ];
    const sel = selectPinnedAlerts(mixed, {
      expanded: false,
      stageId: "boundary_detection",
    });
    expect(sel.allPinned.every((e) => e.stage === "boundary_detection")).toBe(true);
    expect(sel.primaryError?.message).toBe("Error three");
  });
});
