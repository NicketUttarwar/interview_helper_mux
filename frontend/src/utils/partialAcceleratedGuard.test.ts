import { describe, expect, it } from "vitest";
import {
  deliveryOrderViolation,
  isGPublishReviewCheckpoint,
  isPartialAutoCheckpoint,
  isPartialAcceleratedRun,
  isTranscriptReviewCheckpoint,
  resolveOperatorCover,
  shouldAdvanceAfterGatePost,
  shouldBlockOperatorActionsForJob,
  shouldHoldJobRunningFlag,
  shouldShowAcceleratedRunOverlay,
} from "./partialAcceleratedGuard";
import { PARTIAL_MAY_PAUSE_GATES, PARTIAL_MUST_ACT_GATES } from "./partialOperatorGates";
import type { RunData } from "../types";

function run(partial: Record<string, unknown>): RunData {
  return partial as unknown as RunData;
}

const accelerated = { run_mode: "partially-accelerated" as const, partial_auto_driver_active: true };

describe("partialAcceleratedGuard", () => {
  it("detects partially-accelerated runs", () => {
    expect(isPartialAcceleratedRun(run({ meta: { run_mode: "partially-accelerated" } }))).toBe(true);
    expect(isPartialAcceleratedRun(run({ meta: { partial_auto: true } }))).toBe(true);
    expect(isPartialAcceleratedRun(run({ meta: { run_mode: "manual" } }))).toBe(false);
  });

  it("lifts overlay at transcript_review blocking", () => {
    const r = run({
      meta: accelerated,
      journey: { blocking: { blocked: true, reason: "transcript_review", stage_id: "transcript_review" } },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("none");
  });

  it("lifts overlay when transcript_review_pending is set", () => {
    const r = run({
      meta: accelerated,
      transcript_review_pending: true,
    });
    expect(isTranscriptReviewCheckpoint(r)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
  });

  it("lifts overlay for gate job with transcript review message and no stage", () => {
    const r = run({
      meta: accelerated,
      job: {
        status: "gate",
        message: "Analysis paused for transcript review. Correct STT in the GUI.",
      },
    });
    expect(isTranscriptReviewCheckpoint(r)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, null)).toBe(false);
  });

  it("keeps overlay for G-Framing while Partial driver auto-Yes is in flight", () => {
    const r = run({
      meta: accelerated,
      gap_framing_decision_pending: true,
      job: {
        status: "gate",
        stage: "missing_framing",
        message: "Gap framing gate: choose whether to add interviewer framing audio in the GUI",
      },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(false);
    expect(shouldShowAcceleratedRunOverlay(r, null, { jobRunning: true })).toBe(true);
    expect(shouldBlockOperatorActionsForJob(r, true, null)).toBe(true);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("accelerated");
  });

  it("lifts overlay for G-Framing when there is no driver (Manual Yes/No)", () => {
    const r = run({
      meta: { run_mode: "manual" },
      gap_framing_decision_pending: true,
      job: {
        status: "gate",
        stage: "missing_framing",
        message: "Gap framing gate: choose whether to add interviewer framing audio in the GUI",
      },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("none");
    expect(shouldBlockOperatorActionsForJob(r, true, null)).toBe(false);
  });

  it("lifts overlay for G-Framing when operator_must_act is stamped", () => {
    const r = run({
      meta: accelerated,
      gap_framing_decision_pending: true,
      operator_gates: {
        missing_framing: { severity: "hard_block", operator_must_act: true },
      },
      job: { status: "gate", stage: "missing_framing", message: "Gap framing gate" },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("none");
  });

  it("keeps overlay for later framing sub-gates while the driver owns them", () => {
    const pickup = run({
      meta: accelerated,
      pickup_speaker_pending: true,
      job: { status: "gate", stage: "missing_framing", message: "Pickup speaker gate" },
    });
    expect(isPartialAutoCheckpoint(pickup, null)).toBe(false);
    expect(resolveOperatorCover(pickup, null, { jobRunning: true })).toBe("accelerated");

    const voice = run({
      meta: accelerated,
      job: {
        status: "gate",
        stage: "voice_reference",
        message: "Voice reference gate: approve interviewer voice sample before gap framing LLM stages.",
      },
    });
    expect(isPartialAutoCheckpoint(voice, null)).toBe(false);
    expect(resolveOperatorCover(voice, null)).toBe("accelerated");
  });

  it("lifts overlay for pickup speaker when there is no driver", () => {
    const r = run({
      meta: { run_mode: "manual" },
      pickup_speaker_pending: true,
      job: { status: "gate", message: "Pickup speaker gate" },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(resolveOperatorCover(r, null)).toBe("none");
  });

  it("lifts overlay for job.status=gate that is not a driver-owned framing gate", () => {
    const r = run({
      meta: accelerated,
      job: {
        status: "gate",
        stage: "write_approval",
        message: "Write approval required",
      },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(resolveOperatorCover(r, null)).toBe("none");
  });

  it("lifts overlay for needs_operator stage reuse", () => {
    const r = run({
      meta: accelerated,
      job: { status: "needs_operator", needs_stage_reuse: true, stage: "transcribe" },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(true);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("none");
  });

  it("hides overlay while peeking at logs", () => {
    const r = run({
      meta: accelerated,
      journey: { blocking: { blocked: false } },
    });
    expect(shouldShowAcceleratedRunOverlay(r, { pending: false }, { peeking: true })).toBe(false);
    expect(resolveOperatorCover(r, { pending: false }, { peeking: true })).toBe("none");
  });

  it("lifts overlay at g-publish when package ready", () => {
    const r = run({
      meta: accelerated,
    });
    const gPublish = { pending: true, package_ready: true, skipped: false };
    expect(isPartialAutoCheckpoint(r, gPublish)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, gPublish)).toBe(false);
  });

  it("lifts overlay at g-publish when master exists before package_ready", () => {
    const r = run({
      meta: accelerated,
    });
    const gPublish = { pending: true, package_ready: false, has_master: true, skipped: false };
    expect(isPartialAutoCheckpoint(r, gPublish)).toBe(true);
    expect(shouldShowAcceleratedRunOverlay(r, gPublish)).toBe(false);
  });

  it("keeps accelerated overlay at g_publish gate until review payload is ready", () => {
    const r = run({
      meta: { ...accelerated, g_publish_pending: true },
      job: {
        status: "gate",
        stage: "g_publish",
        message: "Final sign-off: listen to the master and check the cover, then Continue or Skip.",
      },
      journey: {
        blocking: {
          blocked: true,
          reason: "llm_gate",
          stage_id: "g_publish",
          message: "Final sign-off: listen to the master and check the cover, then Continue or Skip.",
        },
      },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(false);
    expect(isPartialAutoCheckpoint(r, { pending: true, package_ready: false, has_master: false })).toBe(
      false,
    );
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("accelerated");
    expect(
      resolveOperatorCover(
        r,
        { pending: true, package_ready: false, has_master: true, skipped: false },
        { jobRunning: true },
      ),
    ).toBe("none");
  });

  it("keeps accelerated overlay at g_publish until the review payload can paint", () => {
    const r = run({
      meta: { ...accelerated, g_publish_pending: true },
      job: {
        status: "gate",
        stage: "g_publish",
        message: "Final sign-off: listen to the master and check the cover, then Continue or Skip.",
      },
      journey: {
        blocking: {
          blocked: true,
          reason: "llm_gate",
          stage_id: "g_publish",
          message: "Final sign-off: listen to the master and check the cover, then Continue or Skip.",
        },
      },
      stages: [{ id: "master_finalize", status: "done" }],
    });
    expect(isGPublishReviewCheckpoint(null, r)).toBe(false);
    expect(isPartialAutoCheckpoint(r, null)).toBe(false);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("accelerated");
    expect(shouldShowAcceleratedRunOverlay(r, null, { jobRunning: true })).toBe(true);
  });

  it("keeps Ship checkpoint after Prepare clears the gate (until upload)", () => {
    const r = run({
      meta: { ...accelerated, g_publish_pending: false, g_publish_cleared: true },
      stages: [{ id: "master_finalize", status: "done" }],
    });
    const gPublish = {
      pending: false,
      cleared: true,
      has_master: true,
      package_ready: false,
      skipped: false,
      already_uploaded_count: 0,
    };
    expect(isPartialAutoCheckpoint(r, gPublish)).toBe(true);
    expect(resolveOperatorCover(r, gPublish, { jobRunning: true })).toBe("none");
  });

  it("shows accelerated cover during automated phase", () => {
    const r = run({
      meta: accelerated,
      journey: { blocking: { blocked: false } },
    });
    expect(shouldShowAcceleratedRunOverlay(r, { pending: false })).toBe(true);
    expect(resolveOperatorCover(r, { pending: false }, { jobRunning: true })).toBe("accelerated");
  });

  it("keeps accelerated cover after G-Framing gate while the driver still owns resume", () => {
    const paused = run({
      meta: accelerated,
      job: { status: "gate", message: "Gap framing gate" },
    });
    expect(resolveOperatorCover(paused, null, { jobRunning: true })).toBe("accelerated");
    const resumed = run({
      meta: accelerated,
      job: { status: "running", stage: "missing_framing" },
      journey: { blocking: { blocked: false } },
    });
    expect(resolveOperatorCover(resumed, { pending: false }, { jobRunning: true })).toBe(
      "accelerated",
    );
  });

  it("uses busy cover for a running manual job", () => {
    const r = run({
      meta: { run_mode: "manual" },
      job: { status: "running", stage: "transcribe" },
    });
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("busy");
  });

  it("detects 5C delivery order violations", () => {
    expect(deliveryOrderViolation("vo_synthesize", "vo_line_adjudicate")).toBe(true);
    expect(deliveryOrderViolation("edl_narrative_audit", "vo_synthesize")).toBe(true);
    expect(deliveryOrderViolation("vo_line_adjudicate", "vo_synthesize")).toBe(false);
  });

  it("D-02/HC-6: GUI Continues after a gate POST in Manual, Partial, and Full-auto", () => {
    expect(shouldAdvanceAfterGatePost(run({ meta: { run_mode: "manual" } }))).toBe(true);
    expect(
      shouldAdvanceAfterGatePost(
        run({ meta: { run_mode: "partially-accelerated", partial_auto_driver_active: true } }),
      ),
    ).toBe(true);
    expect(
      shouldAdvanceAfterGatePost(
        run({ meta: { run_mode: "partially-accelerated", partial_auto_driver_active: false } }),
      ),
    ).toBe(true);
  });

  it("HC-6: missing driver flag and Full-auto still GUI-advance; dual walk is the lease", () => {
    expect(
      shouldAdvanceAfterGatePost(run({ meta: { run_mode: "partially-accelerated" } })),
    ).toBe(true);
    expect(
      shouldAdvanceAfterGatePost(
        run({ meta: { run_mode: "partially-accelerated", partial_auto: true } }),
      ),
    ).toBe(true);
    expect(
      shouldAdvanceAfterGatePost(run({ meta: { run_mode: "full-auto", full_auto: true } })),
    ).toBe(true);
    expect(shouldAdvanceAfterGatePost(run({ meta: { full_auto: true } }))).toBe(true);
    expect(shouldAdvanceAfterGatePost(null)).toBe(true);
  });

  it("D-01: must-act SSOT is G0 + g_publish; may-pause covers framing/G1/reuse/write-approval", () => {
    expect([...PARTIAL_MUST_ACT_GATES]).toEqual(["transcript_review", "g_publish"]);
    expect(PARTIAL_MAY_PAUSE_GATES).toContain("gap_framing");
    expect(PARTIAL_MAY_PAUSE_GATES).toContain("g1_vo_pickup");
    expect(PARTIAL_MAY_PAUSE_GATES).toContain("stage_reuse");
    expect(PARTIAL_MAY_PAUSE_GATES).toContain("write_approval");
  });

  it("does not block operator actions at G0 despite stale job.running", () => {
    const r = run({
      meta: { run_mode: "partially-accelerated" },
      transcript_review_pending: true,
      job: { status: "running", message: "transcribe" },
    });
    expect(shouldBlockOperatorActionsForJob(r, true, null)).toBe(false);
    expect(shouldBlockOperatorActionsForJob(r, true, { pending: false })).toBe(false);
    expect(shouldBlockOperatorActionsForJob(r, false, null)).toBe(false);
  });

  it("still blocks operator actions when job is running outside checkpoints", () => {
    const r = run({
      meta: accelerated,
      journey: { blocking: { blocked: false } },
      job: { status: "running", message: "speaker_roles" },
    });
    expect(shouldBlockOperatorActionsForJob(r, true, null)).toBe(true);
  });

  it("does not treat stale blocking as a checkpoint while a job is running", () => {
    const r = run({
      meta: accelerated,
      journey: { blocking: { blocked: true, reason: "unknown_internal" } },
      job: { status: "running", stage: "speaker_roles" },
    });
    expect(isPartialAutoCheckpoint(r, null)).toBe(false);
    expect(resolveOperatorCover(r, null, { jobRunning: true })).toBe("accelerated");
  });

  it("holds the running-job flag while the driver owns G-Framing", () => {
    const r = run({
      meta: accelerated,
      gap_framing_decision_pending: true,
      job: { status: "gate", message: "Gap framing gate" },
    });
    expect(shouldHoldJobRunningFlag(r, r.job, null)).toBe(false);
    expect(
      shouldHoldJobRunningFlag(
        r,
        { status: "running", stage: "missing_framing" },
        null,
      ),
    ).toBe(true);
  });

  it("does not hold the running-job flag at G0", () => {
    const r = run({
      meta: accelerated,
      transcript_review_pending: true,
      job: { status: "gate", message: "Analysis paused for transcript review" },
    });
    expect(shouldHoldJobRunningFlag(r, r.job, null)).toBe(false);
    expect(
      shouldHoldJobRunningFlag(
        r,
        { status: "running", stage: "transcript_review" },
        null,
      ),
    ).toBe(false);
  });
});
