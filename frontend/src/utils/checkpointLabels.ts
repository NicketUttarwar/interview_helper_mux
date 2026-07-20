import type { AttentionKind } from "./attentionQueue";

/** Human primary-button labels for gates and checkpoints. */
export function checkpointPrimaryLabel(
  stageId: string,
  kind: AttentionKind,
  opts?: { fileCount?: number; pickupCount?: number; clipCount?: number },
): string {
  if (kind === "stage_reuse") return "Show reuse options";
  if (kind === "milestone") {
    if (stageId === "assembly_preview") return "Listen to preview";
    return "Continue";
  }
  if (kind === "optional") return "View optional offer";

  switch (stageId) {
    case "transcript_review":
      return opts?.clipCount
        ? `Accept all & proceed (${opts.clipCount} clip${opts.clipCount === 1 ? "" : "s"} pending)`
        : "Accept all & proceed";
    case "g1_vo_pickup":
      return opts?.pickupCount
        ? `Record ${opts.pickupCount} pickup line${opts.pickupCount === 1 ? "" : "s"}`
        : "Record pickup lines";
    case "missing_framing":
      return "Confirm gap pickup speaker";
    case "sfx_prompt_craft":
      return "Review SFX prompts";
    default:
      return kind === "blocked" ? "Resolve blocker" : "Open checkpoint";
  }
}

export function guidanceActionLabel(
  kind?: string,
  stageId?: string,
): string {
  if (kind === "run") return "Run now";
  if (kind === "checkpoint" && stageId) {
    return checkpointPrimaryLabel(stageId, "gate");
  }
  if (stageId) return "Go to step";
  return "Open";
}
