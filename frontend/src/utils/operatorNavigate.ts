import type { PipelineSubTab } from "../types";
import type { PendingAction } from "./pendingAction";
import { resolveFocusStepId } from "./resolveActiveStep";
import type { RunData } from "../types";

export interface OperatorNavigateHandlers {
  selectStage: (stageId: string, opts?: { stepId?: string | null }) => void | Promise<void>;
  setActiveTab: (tab: "pipeline") => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  setActiveStepId?: (stepId: string | null) => void;
  openActionModal: () => void;
  closeActionModal: () => void;
  approveWrite?: (stageId: string) => void | Promise<void>;
  acknowledgeHandoff?: () => void | Promise<void>;
}

function stepIdForPending(pending: PendingAction, run?: RunData | null): string | null {
  if (run) {
    const resolved = resolveFocusStepId(run, pending.stageId, {
      blockingReason: pending.kind === "write_approval" ? "write_approval" : pending.kind,
    });
    if (resolved) return resolved;
  }
  switch (pending.kind) {
    case "write_approval":
      return "write_approval";
    case "stage_reuse":
      return "reuse";
    case "handoff":
      return "handoff";
    default:
      return null;
  }
}

function focusWorkbenchStep(
  pending: PendingAction,
  handlers: OperatorNavigateHandlers,
  subTab: PipelineSubTab = "stage",
  run?: RunData | null,
): void {
  const stepId = stepIdForPending(pending, run);
  void handlers.selectStage(pending.stageId, { stepId });
  handlers.setPipelineSubTab(subTab);
  if (stepId) handlers.setActiveStepId?.(stepId);
}

/** Move the GUI to the right place for a pending operator action. */
export function navigateForPendingAction(
  pending: PendingAction,
  handlers: OperatorNavigateHandlers,
  opts: { openModal?: boolean; run?: RunData | null } = {},
): void {
  handlers.setActiveTab("pipeline");

  switch (pending.kind) {
    case "write_approval":
      focusWorkbenchStep(pending, handlers, "stage", opts.run);
      if (opts.openModal) handlers.openActionModal();
      break;
    case "handoff":
      focusWorkbenchStep(pending, handlers, "stage", opts.run);
      handlers.closeActionModal();
      requestAnimationFrame(() => {
        document.getElementById("stage-handoff-panel")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
      break;
    case "stage_reuse":
      focusWorkbenchStep(pending, handlers, "stage", opts.run);
      requestAnimationFrame(() => {
        document.querySelector(".stage-reuse-section")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
      break;
    case "gate":
    case "blocked":
      focusWorkbenchStep(
        pending,
        handlers,
        pending.subTab === "story"
          ? "story"
          : pending.subTab === "timeline"
            ? "timeline"
            : pending.subTab === "profile"
              ? "profile"
              : "stage",
        opts.run,
      );
      if (opts.openModal !== false) handlers.openActionModal();
      break;
    default:
      focusWorkbenchStep(pending, handlers, pending.subTab ?? "stage", opts.run);
      if (opts.openModal) handlers.openActionModal();
  }
}

/** Primary click for a pending action — save, acknowledge, or navigate. */
export function primaryClickForPendingAction(
  pending: PendingAction,
  handlers: OperatorNavigateHandlers,
): void {
  switch (pending.kind) {
    case "write_approval":
      if (handlers.approveWrite) void handlers.approveWrite(pending.stageId);
      else navigateForPendingAction(pending, handlers, { openModal: true });
      return;
    case "handoff":
      navigateForPendingAction(pending, handlers);
      return;
    case "stage_reuse":
      navigateForPendingAction(pending, handlers);
      return;
    default:
      navigateForPendingAction(pending, handlers, { openModal: true });
  }
}
