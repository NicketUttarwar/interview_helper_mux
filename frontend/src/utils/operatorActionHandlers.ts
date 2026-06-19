import type { ExecuteBody } from "../types";
import type { OperatorAction } from "../types/operatorAction";

export interface OperatorActionHandlers {
  openModal: (stageId?: string | null, substepId?: string | null) => void;
  runStage: (stageId: string) => void;
  continueNext: () => void;
  viewLogs: () => void;
  skipOptional?: (stageId: string) => void;
}

function scrollToCheckpoint(substepId?: string | null, blockingReason?: string): void {
  if (typeof document === "undefined") return;
  const scroll = () => {
    let target: Element | null = null;
    if (blockingReason === "stage_reuse" || substepId?.includes("stage_reuse")) {
      target = document.querySelector(".stage-reuse-section");
    } else if (blockingReason === "write_approval" || substepId?.includes("write_approval")) {
      target = document.getElementById("write-approval-panel");
    } else if (blockingReason === "handoff_review" || substepId?.includes("handoff")) {
      target = document.getElementById("stage-handoff-panel");
    } else if (substepId?.includes("preclean")) {
      target = document.querySelector(".preclean-offer-card");
    } else {
      target = document.getElementById("stage-gate-panel");
    }
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(scroll);
  } else {
    scroll();
  }
}

export function invokeOperatorActionPrimary(
  action: OperatorAction,
  handlers: OperatorActionHandlers,
): void {
  switch (action.primaryKind) {
    case "open_modal":
      handlers.openModal(action.stageId, action.substepId);
      scrollToCheckpoint(action.substepId, action.blockingReason);
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

export { scrollToCheckpoint };
