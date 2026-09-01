import type { AttentionKind } from "./attentionQueue";

/** Human primary-button labels for gates and checkpoints. */
export function checkpointPrimaryLabel(
  stageId: string,
  kind: AttentionKind,
  opts?: {
    fileCount?: number;
    pickupCount?: number;
    clipCount?: number;
    /** Header / workflow chips navigate only; workbench banner+footer complete. */
    intent?: "navigate" | "complete";
  },
): string {
  const intent = opts?.intent ?? "navigate";
  if (kind === "stage_reuse") return "Show reuse options";
  if (kind === "milestone") {
    if (stageId === "assembly_preview") return "Listen to preview";
    return "Continue";
  }
  if (kind === "optional") return "View optional offer";

  switch (stageId) {
    case "transcript_review":
      if (intent === "complete") {
        return opts?.clipCount
          ? `Accept all & proceed (${opts.clipCount} clip${opts.clipCount === 1 ? "" : "s"} pending)`
          : "Accept all & proceed";
      }
      return opts?.clipCount
        ? `Open transcript review (${opts.clipCount} clips)`
        : "Open transcript review";
    case "g1_vo_pickup":
      if (opts?.intent === "complete") {
        return opts?.pickupCount
          ? `Synthesize or skip ${opts.pickupCount} gap line(s)`
          : "Continue without gap VO";
      }
      return opts?.pickupCount
        ? `Gap VO optional (${opts.pickupCount} lines)`
        : "Gap VO (optional)";
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
