import { describe, expect, it } from "vitest";
import {
  findNextRunnableStage,
  isActionableIncomplete,
  isOptionalStageSkipped,
  precleanDismissedAtCheckpoint,
} from "./preclean";
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

  it("does not teleport to distant incomplete when earlier pending exists", () => {
    const stages: StageInfo[] = [
      {
        id: "source_acoustic_profile",
        title: "Source acoustic profile",
        description: "",
        status: "pending",
        phase: "analysis",
      },
      {
        id: "interview_spine_build",
        title: "Interview spine",
        description: "",
        status: "locked",
        phase: "analysis",
      },
      {
        id: "g1_5_preview_pickup",
        title: "Post-preview pickup (G1.5)",
        description: "",
        status: "incomplete",
        phase: "gate",
        incomplete_reason: "understanding/gap_report.json is pending",
      },
    ];
    expect(isActionableIncomplete(stages, stages[2])).toBe(false);
    expect(findNextRunnableStage(stages)?.id).toBe("source_acoustic_profile");
  });

  it("treats stage_output_mode optional_skipped as skipped", () => {
    const stage: StageInfo = {
      id: "g1_5_preview_pickup",
      title: "Post-preview pickup (G1.5)",
      description: "",
      status: "done",
      stage_output_mode: "optional_skipped",
    };
    expect(isOptionalStageSkipped(stage, {})).toBe(true);
  });

  it("offers audio_preclean first on cold start", () => {
    const stages: StageInfo[] = [
      {
        id: "audio_preclean",
        title: "Audio pre-clean",
        description: "",
        status: "pending",
        phase: "prepare",
      },
      {
        id: "ingest",
        title: "Ingest",
        description: "",
        status: "pending",
        phase: "prepare",
      },
    ];
    expect(findNextRunnableStage(stages, {})?.id).toBe("audio_preclean");
  });

  it("does not block downstream when optional pre-clean was dismissed", () => {
    const stages: StageInfo[] = [
      {
        id: "audio_preclean",
        title: "Audio pre-clean",
        description: "",
        status: "pending",
        phase: "prepare",
      },
      {
        id: "ingest",
        title: "Ingest",
        description: "",
        status: "done",
        phase: "prepare",
      },
      {
        id: "interview_spine_build",
        title: "Interview spine",
        description: "",
        status: "pending",
        phase: "understand",
      },
    ];
    const meta = {
      audio_preclean: {
        decisions: [{ checkpoint: "before_ingest", action: "dismiss" }],
      },
    };
    expect(findNextRunnableStage(stages, meta)?.id).toBe("interview_spine_build");
  });
});
