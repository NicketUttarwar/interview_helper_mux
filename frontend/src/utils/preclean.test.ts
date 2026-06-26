import { describe, expect, it } from "vitest";
import { findNextRunnableStage, isOptionalStageSkipped, precleanDismissedAtCheckpoint } from "./preclean";
import type { StageInfo } from "../types";

describe("preclean", () => {
  it("detects dismissed before_ingest as skipped optional stage", () => {
    const stage: StageInfo = {
      id: "audio_preclean",
      title: "Audio pre-clean",
      description: "",
      status: "pending",
    };
    const meta = {
      audio_preclean: {
        decisions: [{ checkpoint: "before_ingest", action: "dismiss" }],
      },
    };
    expect(precleanDismissedAtCheckpoint(meta.audio_preclean, "before_ingest")).toBe(true);
    expect(isOptionalStageSkipped(stage, meta)).toBe(true);
  });

  it("does not mark stage skipped when offer unsettled", () => {
    const stage: StageInfo = {
      id: "audio_preclean",
      title: "Audio pre-clean",
      description: "",
      status: "pending",
    };
    expect(isOptionalStageSkipped(stage, {})).toBe(false);
  });

  it("prioritizes action_required gates before pending automated stages", () => {
    const stages: StageInfo[] = [
      {
        id: "transcript_review_build",
        title: "STT review prep",
        description: "",
        status: "done",
        phase: "analysis",
      },
      {
        id: "transcript_review",
        title: "Transcript review",
        description: "",
        status: "action_required",
        phase: "gate",
      },
      {
        id: "disfluency_extract",
        title: "Disfluency extract",
        description: "",
        status: "pending",
        phase: "analysis",
      },
    ];
    expect(findNextRunnableStage(stages)?.id).toBe("transcript_review");
  });
});
