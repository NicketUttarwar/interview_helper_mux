import { describe, expect, it } from "vitest";
import type { StageInfo } from "../types";
import {
  firstUpstreamBlocker,
  stageArtifactsFullyComplete,
  stageHasCommittedOutputs,
  stageIncompleteReason,
  upstreamArtifactsReady,
} from "./stageOutputs";

function stage(partial: Partial<StageInfo> & { id: string }): StageInfo {
  return {
    title: partial.id,
    description: "",
    status: "pending",
    ...partial,
  };
}

describe("stageOutputs", () => {
  it("stageHasCommittedOutputs false when outputs pending", () => {
    const s = stage({
      id: "speaker_roles",
      status: "done",
      outputs_view: [
        { path: "understanding/speakers.json", label: "speakers", status: "pending", phase: "missing", kind: "file" },
      ],
    });
    expect(stageHasCommittedOutputs(s)).toBe(false);
  });

  it("stageIncompleteReason for incomplete status", () => {
    const s = stage({
      id: "speaker_roles",
      status: "incomplete",
      incomplete_reason: "understanding/speakers.json is pending",
    });
    expect(stageIncompleteReason(s)).toContain("speakers.json");
  });

  it("upstreamArtifactsReady false when prior done stage missing outputs", () => {
    const stages = [
      stage({
        id: "speaker_roles",
        status: "done",
        artifacts: ["understanding/speakers.json"],
        artifacts_status: { "understanding/speakers.json": "pending" },
      }),
      stage({ id: "content_context", status: "pending" }),
    ];
    expect(upstreamArtifactsReady(stages, "content_context")).toBe(false);
  });

  it("upstreamArtifactsReady false when prior done stage has partial artifacts", () => {
    const stages = [
      stage({
        id: "speaker_roles",
        status: "done",
        artifacts: ["understanding/speakers.json"],
        artifacts_status: { "understanding/speakers.json": "partial" },
      }),
      stage({ id: "content_context", status: "pending" }),
    ];
    expect(stageArtifactsFullyComplete(stages[0])).toBe(false);
    expect(upstreamArtifactsReady(stages, "content_context")).toBe(false);
  });

  it("firstUpstreamBlocker ignores dismissed optional pre-clean still marked pending", () => {
    const stages = [
      stage({
        id: "audio_preclean",
        title: "Audio pre-clean",
        status: "pending",
        phase: "prepare",
      }),
      stage({ id: "ingest", status: "done", phase: "prepare" }),
      stage({ id: "interview_spine_build", status: "pending", phase: "understand" }),
    ];
    const meta = {
      audio_preclean: {
        decisions: [{ checkpoint: "before_ingest", action: "dismiss" }],
      },
    };
    expect(firstUpstreamBlocker(stages, "interview_spine_build", meta)).toBeNull();
  });
});
