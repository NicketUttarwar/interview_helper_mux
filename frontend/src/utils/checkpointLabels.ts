import type { AttentionKind } from "./attentionQueue";

/** Human primary-button labels for gates and checkpoints. */
export function checkpointPrimaryLabel(
  stageId: string,
  kind: AttentionKind,
  opts?: { fileCount?: number; pickupCount?: number; clipCount?: number },
): string {
  const fc = opts?.fileCount;
  if (kind === "write_approval") {
    return fc
      ? `Review ${fc} file${fc === 1 ? "" : "s"}`
      : "Review & approve outputs";
  }
  if (kind === "stage_reuse") return "Choose reuse or run fresh";
  if (kind === "handoff") return "Review outputs";
  if (kind === "milestone") {
    if (stageId === "assembly_preview") return "Listen to preview";
    if (stageId === "analysis_profile") return "Review AI story profile";
    return "Continue";
  }
  if (kind === "optional") return "View optional offer";

  switch (stageId) {
    case "transcript_review":
      return opts?.clipCount
        ? `Review ${opts.clipCount} STT clip${opts.clipCount === 1 ? "" : "s"}`
        : "Review STT clips";
    case "disfluency_review":
      return "Review filler clips";
    case "g1_vo_pickup":
      return opts?.pickupCount
        ? `Record ${opts.pickupCount} pickup line${opts.pickupCount === 1 ? "" : "s"}`
        : "Record pickup lines";
    case "g2_flow_select":
      return "Confirm output type";
    case "analysis_profile":
      return "Review AI story profile";
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
  if (kind === "profile") return "Open profile";
  if (kind === "story_board") return "Open Story Board";
  if (kind === "checkpoint" && stageId) {
    return checkpointPrimaryLabel(stageId, "gate");
  }
  if (stageId) return "Go to step";
  return "Open";
}
