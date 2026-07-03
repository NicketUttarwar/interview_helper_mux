import { describe, expect, it } from "vitest";
import { findPendingFocusStage, resolveOperatorFocusStageId } from "./checkpoint";
import { resolveOperatorAction } from "./resolveOperatorAction";
import type { RunData } from "../types";

function minimalRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_001_test",
    stages: [],
    ...overrides,
  };
}

describe("findPendingFocusStage", () => {
  it("returns transcribe when journey blocking reason is stage_reuse", () => {
    const run = minimalRun({
      stages: [
        {
          id: "ingest",
          title: "Ingest",
          description: "",
          status: "done",
        },
        {
          id: "transcribe",
          title: "Transcribe",
          description: "",
          status: "pending",
        },
      ],
      job: { status: "complete" },
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "Choose reuse",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "transcribe",
          message: "Transcribe can reuse outputs from exec_000.",
        },
      },
    });
    expect(findPendingFocusStage(run)).toBe("transcribe");
  });

  it("aligns with resolver.stageId for write approval", () => {
    const run = minimalRun({
      stages: [
        {
          id: "ingest",
          title: "Ingest",
          description: "",
          status: "awaiting_write_approval",
        },
      ],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/normalized.wav"],
      },
    });
    const focus = findPendingFocusStage(run);
    const action = resolveOperatorAction(run);
    expect(focus).toBe("ingest");
    expect(action.stageId).toBe("ingest");
    expect(action.mode).toBe("needs_you");
  });

  it("prefers transcript review gate before later pending automated stages", () => {
    const run = minimalRun({
      stages: [
        { id: "ingest", title: "Ingest", description: "", status: "done", phase: "analysis" },
        { id: "transcribe", title: "Transcribe", description: "", status: "done", phase: "analysis" },
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
          status: "locked",
          phase: "analysis",
        },
      ],
      job: { status: "complete" },
    });
    expect(findPendingFocusStage(run)).toBe("transcript_review");
    expect(resolveOperatorAction(run).stageId).toBe("transcript_review");
  });

  it("prefers unacked handoff on done stage before next pending stage", () => {
    const run = minimalRun({
      stages: [
        {
          id: "source_acoustic_profile",
          title: "Source acoustic profile",
          description: "",
          status: "done",
          phase: "understand",
          handoff_paths: ["understanding/source_acoustic_profile.json"],
        },
        {
          id: "interview_spine_build",
          title: "Interview spine",
          description: "",
          status: "pending",
          phase: "understand",
        },
      ],
      job: { status: "complete", stage: "source_acoustic_profile" },
      journey: {
        phase: "understand",
        blocking: {
          blocked: true,
          reason: "stage_reuse",
          stage_id: "interview_spine_build",
          message: "Choose reuse or run fresh",
        },
      },
    });
    expect(findPendingFocusStage(run)).toBe("source_acoustic_profile");
  });

  it("focuses transcript review when job gate is on STT review prep", () => {
    const run = minimalRun({
      stages: [
        { id: "transcript_review_build", title: "STT review prep", description: "", status: "done" },
        {
          id: "transcript_review",
          title: "Transcript review",
          description: "",
          status: "action_required",
          phase: "gate",
        },
      ],
      job: {
        status: "gate",
        stage: "transcript_review_build",
        message:
          "Transcript review required. Open the GUI to correct ranked clips, then complete review.",
      },
      journey: {
        phase: "prepare",
        blocking: {
          blocked: true,
          reason: "transcript_review",
          stage_id: "transcript_review",
          message: "Review 3 ranked STT clips",
        },
      },
    });
    expect(findPendingFocusStage(run)).toBe("transcript_review");
    expect(resolveOperatorFocusStageId(run)).toBe("transcript_review");
  });

  it("focuses upstream stage when gate message references prerequisite failure", () => {
    const run = minimalRun({
      stages: [
        {
          id: "speaker_roles",
          title: "Speaker roles",
          description: "",
          status: "incomplete",
        },
        {
          id: "content_context",
          title: "Content understanding",
          description: "",
          status: "pending",
        },
      ],
      job: {
        status: "gate",
        stage: "content_context",
        message:
          "Prerequisite artifact understanding/speakers.json from stage speaker_roles is incomplete. Use Fill gaps or re-run --from-stage speaker_roles.",
      },
    });
    expect(findPendingFocusStage(run)).toBe("speaker_roles");
  });
});
