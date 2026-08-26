import { describe, expect, it } from "vitest";
import {
  dedupeConsecutiveLogEntries,
  excludePinnedEntries,
  filterLiveStream,
  preferFresherLogTail,
} from "./logStreams";
import { makeLogEntry, makeRunFixture, makeStage } from "../test/runFixtures";

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

describe("preferFresherLogTail", () => {
  it("keeps a longer live tail over a shorter run snapshot", () => {
    const long = [
      makeLogEntry("a", "info", "t1"),
      makeLogEntry("b", "info", "t2"),
      makeLogEntry("c", "info", "t3"),
    ];
    const short = [makeLogEntry("b", "info", "t2")];
    expect(preferFresherLogTail(long, short)).toEqual(long);
    expect(preferFresherLogTail(short, long)).toEqual(long);
  });
});

describe("filterLiveStream", () => {
  it("includes parent-stage and untagged lines while a hitch inner stage runs", () => {
    const run = makeRunFixture({
      stages: [makeStage("edl"), makeStage("chapter_close_hitch")],
      job: {
        status: "running",
        current_stage: "edl",
        parent_stage: "chapter_close_hitch",
      },
    });
    const entries = [
      { ...makeLogEntry("hitch recut", "info", "t1"), stage: "chapter_close_hitch" },
      { ...makeLogEntry("building EDL", "info", "t2"), stage: "edl" },
      makeLogEntry("conductor note", "info", "t3"),
      { ...makeLogEntry("other stage", "info", "t4"), stage: "mix" },
    ];
    const live = filterLiveStream(entries, run, true);
    expect(live.map((e) => e.message)).toEqual([
      "hitch recut",
      "building EDL",
      "conductor note",
    ]);
  });
});
