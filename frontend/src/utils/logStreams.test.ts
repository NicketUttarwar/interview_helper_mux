import { describe, expect, it } from "vitest";
import {
  dedupeConsecutiveLogEntries,
  excludePinnedEntries,
} from "./logStreams";
import { makeLogEntry } from "../test/runFixtures";

describe("logStreams activity dedupe", () => {
  it("excludes pinned timestamps from scroll list", () => {
    const a = makeLogEntry("first error", "error", "t1");
    const b = makeLogEntry("second", "info", "t2");
    const scroll = excludePinnedEntries([a, b], [a]);
    expect(scroll).toEqual([b]);
  });

  it("dedupes consecutive identical message+level lines", () => {
    const dup = makeLogEntry("Coherence report: not found", "error");
    const entries = [dup, dup, dup, makeLogEntry("other", "info")];
    expect(dedupeConsecutiveLogEntries(entries)).toHaveLength(2);
  });
});
