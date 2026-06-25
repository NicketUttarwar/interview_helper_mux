import type { ExecuteBody } from "../types";
import type { OperatorAction } from "../types/operatorAction";
import { scrollToCheckpoint } from "./checkpointScrollRetry";
export interface OperatorActionHandlers {
  openModal: (stageId?: string | null, substepId?: string | null) => void;
  runStage: (stageId: string) => void;
  continueNext: () => void;
  viewLogs: () => void;
  skipOptional?: (stageId: string) => void;
  /** Return true to block the primary action (caller should show toast). */
  guardPrimary?: () => boolean;
}

export function invokeOperatorActionPrimary(
  action: OperatorAction,
  handlers: OperatorActionHandlers,
): void {
  if (handlers.guardPrimary?.()) return;
  switch (action.primaryKind) {
    case "open_modal":
      handlers.openModal(action.stageId, action.substepId);
      scrollToCheckpoint(action.substepId);
      break;
    case "run_stage":
      if (action.stageId) handlers.runStage(action.stageId);
      break;
    case "continue_next":
      handlers.continueNext();
      break;
    case "view_logs":
      handlers.viewLogs();
      break;
    default:
      break;
  }
}

export function invokeOperatorActionSecondary(
  action: OperatorAction,
  handlers: OperatorActionHandlers,
): void {
  switch (action.secondaryKind) {
    case "view_logs":
      handlers.viewLogs();
      break;
    case "skip_optional":
      if (action.stageId && handlers.skipOptional) handlers.skipOptional(action.stageId);
      break;
    default:
      break;
  }
}

export function executeBodyForStage(stageId: string): ExecuteBody {
  return { mode: "stage", stage: stageId };
}

export { scrollToCheckpoint } from "./checkpointScrollRetry";
