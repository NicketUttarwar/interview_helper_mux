import type { RunData } from "../types";
import { gapFillSkipped } from "./stageVisibility";

/** Extra operator hint appended after a job completes (stage-specific). */
export function jobCompletionHint(
  completedStageId: string | undefined,
  refreshed: RunData | null,
): string | null {
  if (!completedStageId || !refreshed) return null;

  if (completedStageId === "transcript_review_build") {
    return "Transcript review needed — correct speech-to-text before continuing.";
  }
  if (completedStageId === "content_context" && refreshed.story_board_ready) {
    return "Story Board unlocked — review themes in the Story tab.";
  }
  if (completedStageId === "segment_classification" && refreshed.timeline_ready) {
    return "Timeline unlocked — open the Timeline tab to review segments.";
  }
  if (
    completedStageId === "delivery_brief_build" &&
    gapFillSkipped(refreshed)
  ) {
    return "Gap-fill skipped — continue to interview profile and flow selection.";
  }
  if (completedStageId === "assembly_preview") {
    return "Listen to the assembly preview before sound design spend.";
  }

  const blocking = refreshed.journey?.blocking;
  if (blocking?.blocked && blocking.message) {
    return blocking.message;
  }
  return null;
}
