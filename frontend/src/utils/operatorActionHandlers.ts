import type { ExecuteBody } from "../types";
import type { OperatorAction } from "../types/operatorAction";
export interface OperatorActionHandlers {
  openModal: (stageId?: string | null, substepId?: string | null) => void;
  runStage: (stageId: string) => void;
  continueNext: () => void;
  viewLogs: () => void;
  skipOptional?: (stageId: string) => void;
  /** Return true to block the primary action (caller should show toast). */
  guardPrimary?: () => boolean;
}

function scrollToCheckpoint(substepId?: string | null, _blockingReason?: string): void {
  if (typeof document === "undefined") return;
  const raw = substepId?.includes(":") ? substepId.split(":").pop() : substepId;
  const scroll = () => {
    const target =
      (raw ? document.querySelector(`[data-testid="stage-step-${raw}"]`) : null) ??
      document.querySelector(".stage-step-row--active");
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const runScroll = () => {
    scroll();
    window.setTimeout(scroll, 120);
    window.setTimeout(scroll, 320);
  };
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(runScroll);
  } else {
    runScroll();
  }
}

export function invokeOperatorActionPrimary(
  action: OperatorAction,
  handlers: OperatorActionHandlers,
): void {
  if (handlers.guardPrimary?.()) return;
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
