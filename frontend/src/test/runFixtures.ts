import type { LogEntry, RunData, TimelineData } from "../types";

/** Minimal run payload for navigation / availability matrix tests. */
export function makeRunFixture(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test_fixture",
    stages: [
      { id: "ingest", title: "Ingest", status: "done" },
      { id: "content_context", title: "Content", status: "pending" },
      { id: "segment_classification", title: "Classify", status: "pending" },
      { id: "analysis_profile", title: "Profile", status: "locked" },
    ],
    ...overrides,
  };
}

export function makeTimelineFixture(segments = 0): TimelineData {
  return {
    segments: Array.from({ length: segments }, (_, i) => ({
      segment_id: `seg_${i}`,
      start_ms: i * 1000,
      end_ms: (i + 1) * 1000,
      text: "sample",
    })),
    duration_ms: segments * 1000,
  };
}

export function makeLogEntry(
  message: string,
  level = "info",
  ts = "2026-06-22T12:00:00.000Z",
): LogEntry {
  return { ts, message, level };
}
