import type { PipelineSubTab, RunData, TimelineData } from "../types";

export interface SubTabAvailability {
  available: boolean;
  reason?: string;
  prerequisiteStageId?: string;
}

function storyReadyFallback(run: RunData): boolean {
  const contentDone = run.stages?.find((s) => s.id === "content_context")?.status === "done";
  return Boolean(contentDone && run.analysis_complete);
}

function timelineReadyFallback(timeline: TimelineData | null): boolean {
  return (timeline?.segments?.length ?? 0) > 0;
}

export function pipelineSubTabAvailability(
  tab: PipelineSubTab,
  run: RunData | null,
  timeline: TimelineData | null,
): SubTabAvailability {
  if (!run) {
    return { available: false, reason: "No active run" };
  }

  switch (tab) {
    case "stage":
    case "files":
    case "llm_calls":
    case "volley_memory":
      return { available: true };
    case "story": {
      const ready = run.story_board_ready ?? storyReadyFallback(run);
      return ready
        ? { available: true }
        : {
            available: false,
            reason: "Unlocks after content understanding",
            prerequisiteStageId: "content_context",
          };
    }
    case "timeline": {
      const ready = run.timeline_ready ?? timelineReadyFallback(timeline);
      return ready
        ? { available: true }
        : {
            available: false,
            reason: "Unlocks after segment classification",
            prerequisiteStageId: "segment_classification",
          };
    }
    case "profile": {
      const ready = Boolean(run.profile_ready_for_review || run.profile_verified);
      return ready
        ? { available: true }
        : {
            available: false,
            reason: "Unlocks when analysis profile is ready for review",
            prerequisiteStageId: "analysis_profile",
          };
    }
    default:
      return { available: true };
  }
}

export function clampPipelineSubTab(
  tab: PipelineSubTab,
  run: RunData | null,
  timeline: TimelineData | null,
): PipelineSubTab {
  const avail = pipelineSubTabAvailability(tab, run, timeline);
  return avail.available ? tab : "stage";
}
