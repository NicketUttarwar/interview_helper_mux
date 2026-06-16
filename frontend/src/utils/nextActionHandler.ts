import type { ExecuteBody, RunData } from "../types";
import { hintToExecuteBody } from "./executeHint";
import { topAttentionItem } from "./attentionQueue";

export interface NextActionHandlers {
  onOpenCheckpoint: (stageId?: string) => void;
  onExecute: (body: ExecuteBody) => void;
  onRunNext: () => void;
  onAcknowledgeHandoff: () => void;
  onGoPipeline: () => void;
  onGoStory: () => void;
  onGoProfile: () => void;
  onScrollPreview: () => void;
}

export interface NextActionClick {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

const PREVIEW_ACTIONS = new Set([
  "Listen to preview, then approve sound",
  "Listen to preview, then approve sound.",
]);

const STORY_ACTIONS = new Set([
  "Review AI story profile",
  "Resolve open questions in Story Board",
]);

/** Map journey.next_action to a concrete click handler. */
export function resolveNextActionClick(
  run: RunData | null,
  handlers: NextActionHandlers,
): NextActionClick | null {
  if (!run) return null;

  const nextAction = run.journey?.next_action?.trim();
  const hint = run.journey?.execute_hint;
  const top = topAttentionItem(run);

  if (top && (run.journey?.blocking?.blocked || top.kind !== "milestone")) {
    return {
      label: top.primaryLabel,
      onClick: () => {
        handlers.onOpenCheckpoint(top.stageId);
      },
    };
  }

  if (hint?.action === "checkpoint" && hint.stage_id) {
    return {
      label: hint.label || nextAction || "Open checkpoint",
      onClick: () => handlers.onOpenCheckpoint(hint.stage_id),
    };
  }

  const body = hint ? hintToExecuteBody(hint) : null;
  if (hint && body) {
    return {
      label: hint.label || nextAction || "Run next step",
      onClick: () => handlers.onExecute(body),
    };
  }

  if (nextAction && PREVIEW_ACTIONS.has(nextAction)) {
    return {
      label: nextAction,
      onClick: handlers.onScrollPreview,
    };
  }

  if (nextAction && STORY_ACTIONS.has(nextAction)) {
    return {
      label: nextAction,
      onClick: () => {
        handlers.onGoStory();
        if (nextAction.includes("profile")) handlers.onGoProfile();
      },
    };
  }

  if (nextAction) {
    return {
      label: nextAction,
      onClick: handlers.onGoPipeline,
    };
  }

  return null;
}
