import type { ExecuteBody } from "../types";
import type { OperatorAction } from "../types/operatorAction";

export interface OperatorActionHandlers {
  openModal: (stageId?: string | null, substepId?: string | null) => void;
  runStage: (stageId: string) => void;
  continueNext: () => void;
  viewLogs: () => void;
}

export function invokeOperatorActionPrimary(
  action: OperatorAction,
  handlers: OperatorActionHandlers,
): void {
  switch (action.primaryKind) {
    case "open_modal":
      handlers.openModal(action.stageId, action.substepId);
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

export function executeBodyForStage(stageId: string): ExecuteBody {
  return { mode: "stage", stage: stageId };
}
