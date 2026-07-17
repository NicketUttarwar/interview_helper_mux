import type { GuidanceItem, StageGuidance, RunMeta, StageInfo } from "../types";
import { isOptionalStageSkipped } from "./preclean";

function itemCategory(item: GuidanceItem): string {
  return item.category || "upstream";
}

export function upstreamGuidanceHasTodo(guidance?: StageGuidance | null): boolean {
  if (!guidance) return false;
  const items = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  return items.some((i) => i.status === "todo" && itemCategory(i) === "upstream");
}

export function stageHealthHasTodo(guidance?: StageGuidance | null): boolean {
  if (!guidance) return false;
  return (guidance.prerequisites || []).some(
    (i) => i.status === "todo" && itemCategory(i) === "stage_health",
  );
}

export function guidanceHasTodo(guidance?: StageGuidance | null): boolean {
  if (!guidance) return false;
  const items = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  return items.some((i) => i.status === "todo");
}

export function stageHasTodoActions(stage: StageInfo, meta?: RunMeta | null): boolean {
  if (stage.stage_output_mode === "optional_skipped") return false;
  if (isOptionalStageSkipped(stage, meta)) return false;
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

export function firstUpstreamTodoItem(guidance?: StageGuidance | null): GuidanceItem | null {
  return (
    flattenGuidanceItems(guidance).find(
      (i) => i.status === "todo" && itemCategory(i) === "upstream",
    ) ?? null
  );
}

export function firstStageHealthTodoItem(guidance?: StageGuidance | null): GuidanceItem | null {
  return (
    (guidance?.prerequisites || []).find(
      (i) => i.status === "todo" && itemCategory(i) === "stage_health",
    ) ?? null
  );
}
