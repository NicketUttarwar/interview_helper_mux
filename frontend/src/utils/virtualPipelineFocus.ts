import type { PipelineSubTab } from "../types";

/** Attention-queue stage ids that are not real pipeline stages. */
export const VIRTUAL_PIPELINE_FOCUS: Record<string, { subTab: PipelineSubTab; label: string }> = {
  investigation_queue: { subTab: "story", label: "Story Board" },
};

export function isVirtualPipelineStage(stageId: string | null | undefined): boolean {
  return Boolean(stageId && stageId in VIRTUAL_PIPELINE_FOCUS);
}

export function resolveVirtualPipelineFocus(
  stageId: string,
): { subTab: PipelineSubTab; label: string } | null {
  return VIRTUAL_PIPELINE_FOCUS[stageId] ?? null;
}
