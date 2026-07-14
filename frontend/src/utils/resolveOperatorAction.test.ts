import { describe, expect, it } from "vitest";
import type { RunData, StageInfo } from "../types";
import {
  resolveOperatorAction,
  resolveOperatorActionForStage,
  focusStageIdFromAction,
  stepModeLabel,
} from "./resolveOperatorAction";

function stage(id: string, status: StageInfo["status"], title = id): StageInfo {
  return {
    id,
    title,
    description: "",
    status,
    operator_phase: "prepare",
  };
}

function baseRun(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "exec_test",
    stages: [
      stage("audio_preclean", "done", "Audio pre-clean"),
      stage("ingest", "pending", "Ingest"),
      stage("transcribe", "locked", "Transcribe"),
    ],
    ...overrides,
  };
}

describe("resolveOperatorAction", () => {
  it("returns idle prompt when no run", () => {
    const a = resolveOperatorAction(null);
    expect(a.headline).toMatch(/Open a run/);
  });

  it("running job maps to running mode", () => {
    const run = baseRun({
      job: {
        status: "running",
        stage: "ingest",
        message: "Normalizing audio…",
        stage_index: 2,
        stage_total: 10,
      },
    });
    const a = resolveOperatorAction(run, { jobRunning: true });
    expect(a.mode).toBe("running");
    expect(a.stageId).toBe("ingest");
    expect(a.primaryDisabled).toBe(true);
    expect(a.progress?.current).toBe(2);
  });

  it("running job takes priority over write approval", () => {
    const run = baseRun({
      stages: [stage("ingest", "awaiting_write_approval", "Ingest")],
      job: {
        status: "running",
        stage: "ingest",
        current_stage: "ingest",
        pending_write_stage: "ingest",
        awaiting_write_approval: true,
        message: "Hashing source files",
      },
    });
    const a = resolveOperatorAction(run, { jobRunning: true });
    expect(a.mode).toBe("running");
    expect(a.substepId).not.toBe("write_approval:ingest");
  });

  it("awaiting_write_approval maps to needs_you", () => {
    const run = baseRun({
      stages: [
        stage("ingest", "awaiting_write_approval", "Ingest"),
        stage("transcribe", "locked", "Transcribe"),
      ],
      job: {
        status: "awaiting_write_approval",
        stage: "ingest",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/normalized.wav", "ingest/checksums.json"],
        message: "Stage 'ingest' outputs await review (2 file(s)).",
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.substepId).toBe("write_approval:ingest");
    expect(a.modalAutoOpen).toBe(false);
    expect(a.primaryKind).toBe("open_modal");
    expect(a.headline).toMatch(/Review Ingest/);
  });

  it("stage_reuse maps to needs_you", () => {
    const run = baseRun({
      stages: [
        stage("ingest", "done", "Ingest"),
        stage("transcribe", "pending", "Transcribe"),
      ],
      job: {
        status: "needs_operator",
        stage: "transcribe",
        needs_stage_reuse: true,
        reuse_candidates: [{ run_id: "exec_old", paths: ["transcript/full.json"] }],
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.stageId).toBe("transcribe");
    expect(a.headline).toMatch(/reuse or run fresh/i);
  });

  it("transcript_review gate maps to needs_you", () => {
    const run = baseRun({
      stages: [
        stage("transcript_review", "action_required", "Transcript review"),
      ],
      job: { status: "gate", stage: "transcript_review", message: "G0 pending" },
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.stageId).toBe("transcript_review");
    expect(a.substepId).toBe("gate:transcript_review");
  });

  it("interrupted job shows retry", () => {
    const run = baseRun({
      job: { status: "interrupted", stage: "ingest", message: "Server restarted" },
    });
    const a = resolveOperatorAction(run);
    expect(a.headline).toMatch(/interrupted/i);
    expect(a.primaryKind).toBe("run_stage");
  });

  it("error job maps to error mode with retry", () => {
    const run = baseRun({
      stages: [stage("transcribe", "pending", "Transcribe")],
      job: {
        status: "error",
        stage: "transcribe",
        message: "AWS transcription failed",
        last_error: { message: "AWS transcription failed", stage: "transcribe" },
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("error");
    expect(a.stageId).toBe("transcribe");
    expect(a.substepId).toBe("error");
    expect(a.headline).toMatch(/Transcribe failed/);
    expect(a.subline).toBe("AWS transcription failed");
    expect(a.primaryKind).toBe("run_stage");
    expect(a.secondaryKind).toBe("view_logs");
  });

  it("prefers server active_operator_action", () => {
    const run = baseRun({
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "x",
        blocking: { blocked: false },
        active_operator_action: {
          mode: "needs_you",
          stage_id: "ingest",
          substep_id: "write_approval",
          headline: "Server headline",
          primary_label: "Server primary",
          modal_auto_open: true,
        },
      } as RunData["journey"],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        stage: "ingest",
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.headline).toBe("Server headline");
    expect(a.primaryLabel).toBe("Server primary");
  });
});

describe("resolveOperatorActionForStage", () => {
  it("done ingest shows continue to transcribe", () => {
    const run = baseRun({
      stages: [
        stage("ingest", "done", "Ingest"),
        stage("transcribe", "pending", "Transcribe"),
      ],
    });
    const a = resolveOperatorActionForStage(run, "ingest", {});
    expect(a.mode).toBe("done");
    expect(a.primaryKind).toBe("continue_next");
    expect(a.subline).toMatch(/Transcribe/);
  });

  it("locked transcribe shows waiting", () => {
    const run = baseRun({
      stages: [
        stage("ingest", "pending", "Ingest"),
        stage("transcribe", "locked", "Transcribe"),
      ],
    });
    const a = resolveOperatorActionForStage(run, "transcribe", {});
    expect(a.mode).toBe("locked");
    expect(a.primaryDisabled).toBe(true);
  });
});

describe("stepModeLabel", () => {
  it("maps modes", () => {
    expect(stepModeLabel("needs_you")).toBe("Needs you");
    expect(stepModeLabel("running")).toBe("Running");
    expect(stepModeLabel("done")).toBe("Complete");
    expect(stepModeLabel("locked")).toBe("Waiting");
    expect(stepModeLabel("idle")).toBe("Ready");
    expect(stepModeLabel("error")).toBe("Failed");
  });
});

describe("resolveOperatorAction error mode", () => {
  it("job status error maps to error mode with retry", () => {
    const run = baseRun({
      stages: [stage("ingest", "pending", "Ingest")],
      job: {
        status: "error",
        stage: "ingest",
        message: "Normalization failed",
        last_error: { message: "ffmpeg exit 1" },
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("error");
    expect(a.stageId).toBe("ingest");
    expect(a.headline).toMatch(/Ingest failed/);
    expect(a.subline).toBe("ffmpeg exit 1");
    expect(a.primaryKind).toBe("run_stage");
    expect(a.secondaryKind).toBe("view_logs");
  });

  it("error on selected stage via resolveOperatorActionForStage", () => {
    const run = baseRun({
      stages: [stage("ingest", "pending", "Ingest"), stage("transcribe", "locked", "Transcribe")],
      job: {
        status: "error",
        stage: "ingest",
        message: "Disk full",
      },
    });
    const a = resolveOperatorActionForStage(run, "ingest", {});
    expect(a.mode).toBe("error");
    expect(a.primaryLabel).toMatch(/Retry Ingest/);
  });

  it("non-failing stage stays locked while another stage errored", () => {
    const run = baseRun({
      stages: [stage("ingest", "pending", "Ingest"), stage("transcribe", "locked", "Transcribe")],
      job: {
        status: "error",
        stage: "ingest",
        message: "Disk full",
      },
    });
    const a = resolveOperatorActionForStage(run, "transcribe", {});
    expect(a.mode).toBe("locked");
  });
});

describe("resolveOperatorAction gate branches", () => {
  const gateCases = [
    ["disfluency_review", "Disfluency review"],
    ["g1_vo_pickup", "G1 VO pickup"],
    ["analysis_profile", "Analysis profile"],
  ] as const;

  it.each(gateCases)("action_required %s maps to needs_you", (stageId, title) => {
    const run = baseRun({
      stages: [stage(stageId, "action_required", title)],
      job: { status: "gate", stage: stageId, message: `${title} pending` },
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "x",
        blocking: { blocked: true, stage_id: stageId, reason: stageId },
      } as RunData["journey"],
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.stageId).toBe(stageId);
    expect(a.primaryKind).toBe("open_modal");
    expect(a.modalAutoOpen).toBe(false);
  });

  it("handoff_review blocking maps to needs_you", () => {
    const run = baseRun({
      stages: [
        stage("topic_coverage_audit", "done", "Topic coverage"),
      ],
      journey: {
        phase: "analyze",
        milestones: {},
        next_action: "x",
        blocking: {
          blocked: true,
          stage_id: "topic_coverage_audit",
          reason: "handoff_review",
        },
      } as RunData["journey"],
      log_tail: [{ ts: "t", level: "info", message: "handoff paths", stage: "topic_coverage_audit" }],
      handoff_ack: {},
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.blockingReason).toBe("handoff_review");
  });

  it("write_approval via blocking.reason", () => {
    const run = baseRun({
      stages: [stage("ingest", "awaiting_write_approval", "Ingest")],
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "x",
        blocking: {
          blocked: true,
          stage_id: "ingest",
          reason: "write_approval",
        },
      } as RunData["journey"],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["a.wav"],
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.substepId).toBe("write_approval:ingest");
  });

  it("idle next runnable stage", () => {
    const run = baseRun({
      stages: [
        stage("audio_preclean", "done", "Pre-clean"),
        stage("ingest", "pending", "Ingest"),
      ],
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("idle");
    expect(a.stageId).toBe("ingest");
    expect(a.primaryKind).toBe("run_stage");
  });

  it("pending audio_preclean with offer maps to needs_you preclean", () => {
    const run = baseRun({
      stages: [stage("audio_preclean", "pending", "Audio pre-clean")],
    });
    const global = resolveOperatorAction(run);
    expect(global.mode).toBe("needs_you");
    expect(global.stageId).toBe("audio_preclean");
    expect(global.primaryKind).toBe("open_modal");
    expect(global.blockingReason).toBe("preclean");
    const stageAction = resolveOperatorActionForStage(run, "audio_preclean", {});
    expect(stageAction.mode).toBe("needs_you");
    expect(stageAction.primaryLabel).toBe("Run audio cleaning");
  });

  it("after ingest done global idle when transcribe still locked", () => {
    const run = baseRun({
      stages: [
        stage("audio_preclean", "done", "Pre-clean"),
        stage("ingest", "done", "Ingest"),
        stage("transcribe", "locked", "Transcribe"),
      ],
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("idle");
    const locked = resolveOperatorActionForStage(run, "transcribe", {});
    expect(locked.mode).toBe("locked");
    expect(locked.primaryDisabled).toBe(true);
  });

  it("running_with_warnings uses running mode", () => {
    const run = baseRun({
      job: {
        status: "running_with_warnings",
        stage: "ingest",
        message: "Normalizing with warnings",
      },
    });
    const a = resolveOperatorAction(run, { jobRunning: true });
    expect(a.mode).toBe("running");
  });

  it("job complete recent uses step finished headline path via cmd", () => {
    const run = baseRun({
      job: { status: "complete", stage: "ingest", message: "Ingest done" },
      stages: [stage("ingest", "done", "Ingest"), stage("transcribe", "pending", "Transcribe")],
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("idle");
  });

  it("reuse via journey.blocking.stage_reuse", () => {
    const run = baseRun({
      stages: [stage("transcribe", "pending", "Transcribe")],
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "x",
        blocking: {
          blocked: true,
          stage_id: "transcribe",
          reason: "stage_reuse",
          message: "Choose reuse",
        },
      } as RunData["journey"],
    });
    const a = resolveOperatorAction(run);
    expect(a.mode).toBe("needs_you");
    expect(a.substepId).toBe("stage_reuse:transcribe");
  });

  it("fallback uses journey.next_action", () => {
    const run = baseRun({
      stages: [stage("ingest", "done", "Ingest")],
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "All steps complete",
        blocking: { blocked: false },
      } as RunData["journey"],
    });
    const a = resolveOperatorAction(run);
    expect(a.headline).toContain("All steps complete");
  });
});

describe("resolveOperatorActionForStage extended", () => {
  it("running on non-running stage falls back", () => {
    const run = baseRun({
      job: { status: "running", stage: "ingest", message: "Running ingest" },
      stages: [stage("ingest", "pending", "Ingest"), stage("transcribe", "locked", "Transcribe")],
    });
    const a = resolveOperatorActionForStage(run, "transcribe", { jobRunning: true });
    expect(a.mode).toBe("locked");
  });

  it("write approval on specific stage", () => {
    const run = baseRun({
      stages: [stage("ingest", "awaiting_write_approval", "Ingest")],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["ingest/a.wav", "ingest/b.json"],
      },
    });
    const a = resolveOperatorActionForStage(run, "ingest", {});
    expect(a.mode).toBe("needs_you");
    expect(a.subline).toMatch(/2 staged/);
  });

  it("reuse on transcribe stage", () => {
    const run = baseRun({
      stages: [stage("transcribe", "pending", "Transcribe")],
      job: {
        status: "needs_operator",
        stage: "transcribe",
        needs_stage_reuse: true,
        reuse_candidates: [{ run_id: "old", paths: [] }],
      },
    });
    const a = resolveOperatorActionForStage(run, "transcribe", {});
    expect(a.headline).toMatch(/reuse/i);
  });

  it("gate on selected stage", () => {
    const run = baseRun({
      stages: [stage("transcript_review", "action_required", "Transcript review")],
      job: { status: "gate", stage: "transcript_review" },
    });
    const a = resolveOperatorActionForStage(run, "transcript_review", {});
    expect(a.mode).toBe("needs_you");
    expect(a.headline).toMatch(/speech-to-text|Transcript/i);
  });

  it("pinned non-focus stage shows stage title", () => {
    const run = baseRun({
      stages: [
        stage("ingest", "awaiting_write_approval", "Ingest"),
        stage("transcribe", "locked", "Transcribe"),
      ],
      job: { status: "awaiting_write_approval", pending_write_stage: "ingest" },
    });
    const a = resolveOperatorActionForStage(run, "transcribe", {});
    expect(a.mode).toBe("locked");
  });
});

describe("copy templates", () => {
  it.each([
    ["ingest", "Normalizing audio…", /Running Ingest/],
    ["ingest", "Hashing source files", /Running Ingest/],
    ["transcribe", "Uploading to AWS S3", /Running Transcribe/],
    ["transcribe", "Waiting for AWS Transcribe", /Running Transcribe/],
  ] as const)("running %s — %s", (stageId, message, pattern) => {
    const run = baseRun({
      stages: [stage(stageId, "pending", stageId === "ingest" ? "Ingest" : "Transcribe")],
      job: {
        status: "running",
        stage: stageId,
        current_stage: stageId,
        message,
        stage_index: 2,
        stage_total: 10,
      },
    });
    const a = resolveOperatorAction(run, { jobRunning: true });
    expect(a.headline).toMatch(pattern);
    expect(a.headline).toContain(message.replace(/\.$/, ""));
  });

  it("prefers intra-stage step progress over batch stage index", () => {
    const run = baseRun({
      stages: [stage("disfluency_extract", "pending", "Disfluency extract")],
      job: {
        status: "running",
        stage: "disfluency_extract",
        current_stage: "disfluency_extract",
        message: "Checking gap 45/389 for voice activity…",
        stage_index: 1,
        stage_total: 1,
        phase: "gap_scan",
        step_index: 45,
        step_total: 389,
      },
    });
    const a = resolveOperatorAction(run, { jobRunning: true });
    expect(a.subline).toBe("Checking gap 45/389 for voice activity…");
    expect(a.progress).toEqual({
      current: 45,
      total: 389,
      label: "gap scan",
    });
  });

  it("ingest write approval headline", () => {
    const run = baseRun({
      stages: [stage("ingest", "awaiting_write_approval", "Ingest")],
      job: {
        status: "awaiting_write_approval",
        pending_write_stage: "ingest",
        pending_write_paths: ["a", "b"],
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.headline).toMatch(/Review Ingest outputs before saving/);
    expect(a.subline).toMatch(/2 staged/);
  });

  it("transcribe reuse subline includes candidate count", () => {
    const run = baseRun({
      stages: [stage("transcribe", "pending", "Transcribe")],
      job: {
        status: "needs_operator",
        stage: "transcribe",
        needs_stage_reuse: true,
        reuse_candidates: [
          { run_id: "a", paths: [] },
          { run_id: "b", paths: [] },
        ],
      },
    });
    const a = resolveOperatorAction(run);
    expect(a.subline).toMatch(/2 prior runs/);
  });

  it("analysis_profile gate headline", () => {
    const run = baseRun({
      stages: [stage("analysis_profile", "action_required", "Analysis profile")],
      job: { status: "gate", stage: "analysis_profile" },
    });
    const a = resolveOperatorAction(run);
    expect(a.headline).toMatch(/profile/i);
  });

  it("focusStageIdFromAction matches gate focus", () => {
    const run = baseRun({
      stages: [stage("transcript_review", "action_required", "Transcript review")],
      job: { status: "gate", stage: "transcript_review" },
    });
    expect(focusStageIdFromAction(run)).toBe("transcript_review");
  });

  it("handoff blocking uses handoff substepId", () => {
    const run = baseRun({
      stages: [stage("topic_coverage_audit", "done", "Coverage")],
      journey: {
        phase: "analyze",
        milestones: {},
        next_action: "x",
        blocking: {
          blocked: true,
          stage_id: "topic_coverage_audit",
          reason: "handoff_review",
        },
      } as RunData["journey"],
    });
    const a = resolveOperatorAction(run);
    expect(a.substepId).toBe("handoff:topic_coverage_audit");
  });

  it("idle run stage shows Run label", () => {
    const run = baseRun({
      stages: [
        stage("audio_preclean", "done", "Pre-clean"),
        stage("ingest", "pending", "Ingest"),
      ],
    });
    const a = resolveOperatorActionForStage(run, "ingest", {});
    expect(a.primaryLabel).toMatch(/Run Ingest/);
  });

  it("done ingest continue label", () => {
    const run = baseRun({
      stages: [
        stage("ingest", "done", "Ingest"),
        stage("transcribe", "pending", "Transcribe"),
      ],
    });
    const a = resolveOperatorActionForStage(run, "ingest", {});
    expect(a.primaryLabel).toMatch(/Continue to Transcribe/);
  });

  it("T1-like: incomplete stage with missing outputs offers rerun", () => {
    const run = baseRun({
      stages: [
        {
          ...stage("boundary_detection", "incomplete", "Boundaries"),
          outputs_view: [{ path: "segments/boundaries.json", phase: "missing", status: "pending" }],
        },
        stage("segment_classification", "locked", "Classification"),
      ],
      selected_stage_id: "boundary_detection",
    });
    const a = resolveOperatorActionForStage(run, "boundary_detection", {});
    expect(a.mode).toBe("error");
    expect(a.headline).toMatch(/incomplete/i);
    expect(a.primaryKind).toBe("run_stage");
    expect(a.primaryLabel).toMatch(/Rerun/);
  });

  it("server action with modal_auto_open false", () => {
    const run = baseRun({
      journey: {
        phase: "prepare",
        milestones: {},
        next_action: "x",
        blocking: { blocked: false },
        active_operator_action: {
          mode: "needs_you",
          stage_id: "ingest",
          headline: "Custom",
          primary_label: "Open",
          modal_auto_open: false,
        },
      } as RunData["journey"],
      job: { status: "awaiting_write_approval", pending_write_stage: "ingest", stage: "ingest" },
    });
    const a = resolveOperatorAction(run);
    expect(a.headline).toBe("Custom");
    expect(a.modalAutoOpen).toBe(false);
  });
});
