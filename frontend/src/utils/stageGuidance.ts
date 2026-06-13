import type { GuidanceItem, StageGuidance, StageInfo } from "../types";

export function guidanceHasTodo(guidance?: StageGuidance | null): boolean {
  if (!guidance) return false;
  const items = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  return items.some((i) => i.status === "todo");
}

export function stageHasTodoActions(stage: StageInfo): boolean {
  if (stage.status === "action_required" || stage.status === "awaiting_write_approval") {
    return true;
  }
  return guidanceHasTodo(stage.guidance);
}

export function flattenGuidanceItems(guidance?: StageGuidance | null): GuidanceItem[] {
  if (!guidance) return [];
  return [...(guidance.prerequisites || []), ...(guidance.actions || [])];
}

export function firstTodoItem(guidance?: StageGuidance | null): GuidanceItem | null {
  return flattenGuidanceItems(guidance).find((i) => i.status === "todo") ?? null;
}
