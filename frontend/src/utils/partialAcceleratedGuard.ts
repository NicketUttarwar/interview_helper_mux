import type { RunData } from "../types";

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

/** Operator checkpoint — overlay lifts so transcript review or G-Publish is interactive. */
export function isPartialAutoCheckpoint(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
): boolean {
  if (!run) return false;
  if (isTranscriptReviewCheckpoint(run)) return true;
  if (run.job?.status === "needs_operator") return true;
  if (gPublish?.pending && gPublish.package_ready && !gPublish.skipped) return true;
  return false;
}

export function shouldShowAcceleratedRunOverlay(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
  opts?: { jobRunning?: boolean; peeking?: boolean },
): boolean {
  if (!isPartialAcceleratedRun(run)) return false;
  if (run?.meta?.partial_auto_complete === true) return false;
  if (opts?.peeking) return false;
  if (isPartialAutoCheckpoint(run, gPublish)) return false;

  const driverActive = run?.meta?.partial_auto_driver_active;
  if (driverActive === false && !opts?.jobRunning) return false;

  return driverActive === true || Boolean(opts?.jobRunning) || driverActive == null;
}
