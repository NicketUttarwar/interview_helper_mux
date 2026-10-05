import type { RunData } from "../types";
import { isJobActivelyRunning } from "./jobStatus";
import { gateOperatorMustAct } from "./operatorGates";
import {
  PARTIAL_MAY_PAUSE_GATES,
  PARTIAL_MUST_ACT_GATES,
} from "./partialOperatorGates";

export { PARTIAL_MAY_PAUSE_GATES, PARTIAL_MUST_ACT_GATES } from "./partialOperatorGates";

/** Mirrors backend DELIVERY_ORDER 5C slice for partial-auto guards. */
export const DELIVERY_ORDER_5C: readonly string[] = [
  "vo_line_adjudicate",
  "vo_synthesize",
  "sound_design_vo_finalize",
  "edl_narrative_audit",
  "edl",
  "assembly_preview",
  "listen_delight_audit",
  "music_palette_compose",
  "sfx_prompt_craft",
  "mmaudio_sfx",
  "mix",
  "junction_snip_qa",
  "master_finalize",
];

export function deliveryStageIndex(stageId: string): number {
  return DELIVERY_ORDER_5C.indexOf(stageId);
}

/** True when `before` is earlier in canonical 5C order than `after` (stale progress). */
export function deliveryOrderViolation(after: string, before: string): boolean {
  const ia = deliveryStageIndex(after);
  const ib = deliveryStageIndex(before);
  if (ia < 0 || ib < 0) return false;
  return ib < ia;
}

export interface PartialAutoGPublishState {
  pending?: boolean;
  package_ready?: boolean;
  /** Master wav present — review UI can open before podcast_publish mints package_ready. */
  has_master?: boolean;
  skipped?: boolean;
  already_uploaded_count?: number;
}

/** Operator can open G-Publish review (title/cover) once master exists; package_ready comes after Prepare. */
export function isGPublishReviewCheckpoint(
  gPublish: PartialAutoGPublishState | null | undefined,
): boolean {
  return Boolean(
    gPublish?.pending &&
      !gPublish.skipped &&
      (gPublish.package_ready || gPublish.has_master),
  );
}

/** Job/block is the G-Publish sign-off — not yet the editable review UI. */
export function isGPublishGatePending(run: RunData | null | undefined): boolean {
  if (!run) return false;
  if (run.meta?.g_publish_pending && !run.meta?.g_publish_skipped && !run.meta?.g_publish_cleared) {
    return true;
  }
  const jobStage = String(run.job?.stage || run.job?.current_stage || "");
  if (jobStage === "g_publish" || jobStage === "podcast_publish") return true;
  const blocking = run.journey?.blocking ?? run.blocking;
  const blockStage = String(blocking?.stage_id || "");
  const reason = String(blocking?.reason || "");
  if (reason === "g_publish") return true;
  if (blockStage === "g_publish" || blockStage === "podcast_publish") return true;
  const msg = `${run.job?.message || ""} ${blocking?.message || ""}`.toLowerCase();
  return msg.includes("final sign-off") || msg.includes("g-publish");
}

/** Job statuses that mean the operator must act — overlay must unmount. */
const OPERATOR_JOB_STATUSES = new Set([
  "gate",
  "needs_operator",
  "needs_clarification",
  "awaiting_write_approval",
]);

/** Journey blocking reasons that are operator pauses even if job.running is stale. */
const OPERATOR_BLOCK_REASONS = new Set([
  "transcript_review",
  "g1_vo_pickup",
  "g1_5_preview_pickup",
  "pickup_speaker",
  "llm_gate",
  "stage_reuse",
  "handoff_review",
  "write_approval",
  "operator_decisions",
  "gap_framing",
  "missing_framing",
  "g_publish",
]);

export type OperatorCoverKind = "none" | "busy" | "accelerated";

export function isPartialAcceleratedRun(run: RunData | null | undefined): boolean {
  if (!run?.meta) return false;
  return (
    run.meta.run_mode === "partially-accelerated" ||
    Boolean(run.meta.partial_auto)
  );
}

export function isFullAutoRun(run: RunData | null | undefined): boolean {
  if (!run?.meta) return false;
  return run.meta.run_mode === "full-auto" || Boolean(run.meta.full_auto);
}

function jobLooksLikeTranscriptReview(run: RunData): boolean {
  const msg = `${run.job?.message || ""} ${run.job?.error || ""}`.toLowerCase();
  if (msg.includes("transcript review")) return true;
  const stage = run.job?.stage || run.job?.current_stage;
  return stage === "transcript_review" || stage === "transcript_review_build";
}

/** G0 — overlay must lift so the operator can correct STT. */
export function isTranscriptReviewCheckpoint(run: RunData | null | undefined): boolean {
  if (!run) return false;
  if (run.transcript_review_pending) return true;
  if (run.journey?.blocking?.reason === "transcript_review") return true;
  if (run.blocking?.reason === "transcript_review") return true;
  if (run.job?.status === "gate" && jobLooksLikeTranscriptReview(run)) return true;
  return false;
}

/** True when Full-auto / Partial driver owns G-Framing (auto-Yes) and later sub-gates. */
function driverOwnsFramingFamily(run: RunData): boolean {
  const gate = run.operator_gates?.missing_framing;
  if (gate?.operator_must_act === true) return false;
  if (gate?.severity === "automation_pending") return true;
  if (run.meta?.partial_auto_complete === true) return false;
  if (run.meta?.partial_auto_driver_active === false) return false;
  return Boolean(
    run.meta?.full_auto ||
      run.meta?.partial_auto ||
      run.meta?.partial_auto_driver_active === true ||
      run.meta?.run_mode === "full-auto" ||
      run.meta?.run_mode === "partially-accelerated",
  );
}

function isFramingFamilyJob(run: RunData): boolean {
  const stage = String(run.job?.stage || run.job?.current_stage || "");
  const msg = `${run.job?.message || ""} ${run.job?.error || ""}`.toLowerCase();
  if (stage === "missing_framing" || stage === "voice_reference") return true;
  return (
    msg.includes("gap framing") ||
    msg.includes("pickup speaker") ||
    msg.includes("voice reference") ||
    msg.includes("voice sample")
  );
}

const FRAMING_FAMILY_BLOCK_REASONS = new Set([
  "gap_framing",
  "missing_framing",
  "pickup_speaker",
]);

function blockingNeedsOperator(run: RunData): boolean {
  const blocking = run.journey?.blocking ?? run.blocking;
  if (!blocking?.blocked) return false;
  const reason = String(blocking.reason || "");
  if (reason === "g1_vo_pickup" && !gateOperatorMustAct(run, "g1_vo_pickup")) {
    return false;
  }
  if (FRAMING_FAMILY_BLOCK_REASONS.has(reason) && driverOwnsFramingFamily(run)) {
    return false;
  }
  if (OPERATOR_BLOCK_REASONS.has(reason)) return true;
  return !isJobActivelyRunning(run.job);
}

/**
 * Any pause that requires a human click. Overlay unmounts; buttons must work.
 * After the operator acts, this goes false and the accelerated cover returns.
 *
 * Partial-auto: keep the accelerated cover through delivery until G-Publish
 * review is showable (master/package). Bare `job.status=gate` / `llm_gate` for
 * `g_publish` must not lift early while the review panel cannot mount.
 */
export function isPartialAutoCheckpoint(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
): boolean {
  if (!run) return false;
  if (isTranscriptReviewCheckpoint(run)) return true;
  // Must-act ship review — lift only when title/cover edit UI can mount.
  if (isGPublishReviewCheckpoint(gPublish)) return true;

  const holdOverlayForGPublish =
    isPartialAcceleratedRun(run) &&
    isGPublishGatePending(run) &&
    !isGPublishReviewCheckpoint(gPublish);

  const driverOwns = driverOwnsFramingFamily(run);
  if (run.gap_framing_decision_pending && !driverOwns) return true;
  if (run.pickup_speaker_pending && !driverOwns) return true;
  const status = run.job?.status || "";
  if (OPERATOR_JOB_STATUSES.has(status)) {
    const driverOwnedFramingGate =
      status === "gate" && driverOwns && isFramingFamilyJob(run);
    if (holdOverlayForGPublish) {
      /* keep accelerated cover until review payload is ready */
    } else if (!driverOwnedFramingGate) {
      return true;
    }
  }
  if (run.job?.needs_stage_reuse) return true;
  if (blockingNeedsOperator(run)) {
    if (holdOverlayForGPublish) return false;
    return true;
  }
  return false;
}

/** Stale job.running must not block operator actions at a checkpoint. */
export function shouldBlockOperatorActionsForJob(
  run: RunData | null | undefined,
  jobRunning: boolean,
  gPublish?: PartialAutoGPublishState | null,
): boolean {
  if (!jobRunning) return false;
  if (isPartialAutoCheckpoint(run, gPublish)) return false;
  return true;
}

/** True when the GUI should keep the running-job flag — false at operator pauses. */
export function shouldHoldJobRunningFlag(
  run: RunData | null | undefined,
  job: RunData["job"] | null | undefined,
  gPublish?: PartialAutoGPublishState | null,
): boolean {
  if (!isJobActivelyRunning(job)) return false;
  const merged = run ? { ...run, job: job ?? run.job } : null;
  if (merged && isPartialAutoCheckpoint(merged, gPublish)) return false;
  return true;
}

export function resolveOperatorCover(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
  opts?: { jobRunning?: boolean; peeking?: boolean },
): OperatorCoverKind {
  if (opts?.peeking) return "none";
  if (isPartialAutoCheckpoint(run, gPublish)) return "none";

  const jobRunning = Boolean(opts?.jobRunning);
  if (isPartialAcceleratedRun(run) && run?.meta?.partial_auto_complete !== true) {
    const driverActive = run?.meta?.partial_auto_driver_active;
    if (driverActive === false && !jobRunning) return "none";
    if (driverActive === true || jobRunning || driverActive == null) {
      return "accelerated";
    }
  }
  if (jobRunning) return "busy";
  return "none";
}

export function shouldShowAcceleratedRunOverlay(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
  opts?: { jobRunning?: boolean; peeking?: boolean },
): boolean {
  return resolveOperatorCover(run, gPublish, opts) === "accelerated";
}

/**
 * After a successful gate POST: GUI Continues in Manual, Partial, and Full-auto
 * (operator clicked). Dual walk is the gate_advance_lease, not this flag.
 */
export function shouldAdvanceAfterGatePost(run: RunData | null | undefined): boolean {
  void run;
  return true;
}
