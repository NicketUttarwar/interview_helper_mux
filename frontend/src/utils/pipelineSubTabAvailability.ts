import type { PipelineSubTab, RunData, TimelineData } from "../types";

export interface SubTabAvailability {
  available: boolean;
  reason?: string;
  prerequisiteStageId?: string;
}

function timelineReadyFallback(timeline: TimelineData | null): boolean {
  return (timeline?.segments?.length ?? 0) > 0;
}

/** v2 pipeline exposes stage workbench and NLE timeline only. */
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
      return { available: true };
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
    default:
      return { available: false, reason: "Not available in v2 mode" };
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
