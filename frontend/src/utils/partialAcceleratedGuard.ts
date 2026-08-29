import type { RunData } from "../types";
import { isJobActivelyRunning } from "./jobStatus";

/** Mirrors backend DELIVERY_ORDER 5C slice for partial-auto guards. */
export const DELIVERY_ORDER_5C: readonly string[] = [
  "sound_design_vo_finalize",
  "vo_line_adjudicate",
  "vo_synthesize",
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
  skipped?: boolean;
  already_uploaded_count?: number;
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
]);

export type OperatorCoverKind = "none" | "busy" | "accelerated";

export function isPartialAcceleratedRun(run: RunData | null | undefined): boolean {
  if (!run?.meta) return false;
  return (
    run.meta.run_mode === "partially-accelerated" ||
    Boolean(run.meta.partial_auto)
  );
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

function blockingNeedsOperator(run: RunData): boolean {
  const blocking = run.journey?.blocking ?? run.blocking;
  if (!blocking?.blocked) return false;
  const reason = String(blocking.reason || "");
  if (OPERATOR_BLOCK_REASONS.has(reason)) return true;
  return !isJobActivelyRunning(run.job);
}

/**
 * Any pause that requires a human click. Overlay unmounts; buttons must work.
 * After the operator acts, this goes false and the accelerated cover returns.
 */
export function isPartialAutoCheckpoint(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
): boolean {
  if (!run) return false;
  if (isTranscriptReviewCheckpoint(run)) return true;
  if (run.gap_framing_decision_pending) return true;
  if (run.pickup_speaker_pending) return true;
  const status = run.job?.status || "";
  if (OPERATOR_JOB_STATUSES.has(status)) return true;
  if (run.job?.needs_stage_reuse) return true;
  if (gPublish?.pending && gPublish.package_ready && !gPublish.skipped) return true;
  if (blockingNeedsOperator(run)) return true;
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
