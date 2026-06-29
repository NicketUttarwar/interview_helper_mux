import type { RunData } from "../types";

/** Extra operator hint appended after a job completes (stage-specific). */
export function jobCompletionHint(
  completedStageId: string | undefined,
  refreshed: RunData | null,
): string | null {
  if (!completedStageId || !refreshed) return null;

  if (completedStageId === "transcript_review_build") {
    return "Transcript review needed — correct speech-to-text before continuing.";
  }
  if (completedStageId === "disfluency_extract") {
    const dfPending = refreshed.disfluency_review_pending ?? refreshed.journey?.blocking?.reason === "disfluency_review";
    return dfPending
      ? "Filler catalog saved — confirm or reject clips in Disfluency review."
      : "Filler catalog saved — review already complete.";
  }
  if (completedStageId === "content_context" && refreshed.story_board_ready) {
    return "Story Board unlocked — review themes in the Story tab.";
  }
  if (completedStageId === "segment_classification" && refreshed.timeline_ready) {
    return "Timeline unlocked — open the Timeline tab to review segments.";
  }
  if (
    completedStageId === "optimal_questions" &&
    refreshed.journey?.blocking?.reason === "analysis_profile"
  ) {
    return "Analysis profile gate — verify story on Story Board or Profile tab.";
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
