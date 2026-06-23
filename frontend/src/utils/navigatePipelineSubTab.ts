import type { PipelineSubTab, RunData, TimelineData } from "../types";
import { pipelineSubTabAvailability } from "./pipelineSubTabAvailability";

export interface NavigatePipelineSubTabOpts {
  force?: boolean;
  onNavigate: (tab: PipelineSubTab) => void;
  onBlocked?: (reason: string) => void;
}

/** Single enforcement point for middle-panel tool tab navigation. */
export function navigatePipelineSubTab(
  tab: PipelineSubTab,
  run: RunData | null,
  timeline: TimelineData | null,
  opts: NavigatePipelineSubTabOpts,
): boolean {
  if (!opts.force) {
    const avail = pipelineSubTabAvailability(tab, run, timeline);
    if (!avail.available) {
      opts.onBlocked?.(avail.reason || "This tool is not available yet.");
      return false;
    }
  }
  opts.onNavigate(tab);
  return true;
}
