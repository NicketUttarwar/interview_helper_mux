import type { RunData, PipelineSubTab } from "../types";
import {
  listRequiredAttentionItems,
  topAttentionItem,
  type AttentionItem,
} from "./attentionQueue";

export type PendingActionKind = AttentionItem["kind"];

export interface PendingAction {
  kind: PendingActionKind;
  stageId: string;
  stageTitle: string;
  title: string;
  message: string;
  primaryLabel: string;
  fileCount?: number;
  handoffPaths?: string[];
  subTab?: PipelineSubTab;
}

function parseFileCountFromMessage(msg?: string): number | undefined {
  if (!msg) return undefined;
  const match = msg.match(/\((\d+)\s+file/i);
  return match ? parseInt(match[1], 10) : undefined;
}

export { parseFileCountFromMessage };

function toPendingAction(item: AttentionItem): PendingAction {
  return {
    kind: item.kind,
    stageId: item.stageId,
    stageTitle: item.stageTitle,
    title: item.title,
    message: item.message,
    primaryLabel: item.primaryLabel,
    fileCount: item.fileCount,
    handoffPaths: item.handoffPaths,
    subTab: item.subTab,
  };
}

/** Highest-priority operator action blocking pipeline progress. */
export function resolvePendingAction(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): PendingAction | null {
  const top = topAttentionItem(run, grants);
  return top ? toPendingAction(top) : null;
}

export function stageNeedsPendingAction(
  run: RunData | null,
  stageId: string,
  grants: Record<string, boolean> = {},
): boolean {
  return listRequiredAttentionItems(run, grants).some((i) => i.stageId === stageId);
}
