/**
 * Partial-auto operator gate SSOT (Cluster D / SYN-MODE).
 *
 * MUST_ACT — Partial always waits here (driver never auto-clears).
 * MAY_PAUSE — overlay can lift when these open; not guaranteed every run.
 *
 * Keep in sync with Python `interview_mux.automation_run` and
 * `isPartialAutoCheckpoint` / OPERATOR_* sets in partialAcceleratedGuard.
 */

export const PARTIAL_MUST_ACT_GATES = ["transcript_review", "g_publish"] as const;

export type PartialMustActGate = (typeof PARTIAL_MUST_ACT_GATES)[number];

/** Framing, G1, stage-reuse, write-approval — may pause when open. */
export const PARTIAL_MAY_PAUSE_GATES = [
  "gap_framing",
  "missing_framing",
  "g1_vo_pickup",
  "stage_reuse",
  "write_approval",
] as const;

export type PartialMayPauseGate = (typeof PARTIAL_MAY_PAUSE_GATES)[number];

export const PARTIAL_MUST_ACT_LABEL =
  "transcript review (G0) and S3 / G-Publish consent";

export const PARTIAL_MAY_PAUSE_LABEL =
  "framing, VO pickup, stage reuse, or write-approval";

/** Start / overlay copy: required stops (must-act), without claiming they are the only possible pauses. */
export function partialMustActCopy(): string {
  return `Required stops: ${PARTIAL_MUST_ACT_LABEL}. You may also be prompted for ${PARTIAL_MAY_PAUSE_LABEL}.`;
}

export function partialMustActOverlayCopy(): string {
  return `This cover stays up while the run walks. It lifts for transcript review (G0) and again at Ship for final title/cover edits before publish. Other gates (${PARTIAL_MAY_PAUSE_LABEL}) may also pause. Watch the stage list and Logs for progress.`;
}

export function partialMustActStartHint(): string {
  return `Partially accelerated never auto-accepts ${PARTIAL_MUST_ACT_LABEL}. ${PARTIAL_MAY_PAUSE_LABEL} may also pause when open.`;
}

export function partialMustActStartDesc(): string {
  return `Full-auto speed with required stops for ${PARTIAL_MUST_ACT_LABEL}; may also pause for ${PARTIAL_MAY_PAUSE_LABEL}.`;
}

export function fullAutoG0HonestyCopy(): string {
  return "Full-auto auto-accepts transcript review (G0), bypasses voice-clone consent, builds the master, prepares the package, and uploads this run to S3.";
}
