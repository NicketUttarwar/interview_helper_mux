import type { PipelineSubTab } from "../types";
import type { PendingAction } from "./pendingAction";

export interface OperatorNavigateHandlers {
  selectStage: (stageId: string) => void | Promise<void>;
  setActiveTab: (tab: "pipeline") => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  openActionModal: () => void;
  closeActionModal: () => void;
  approveWrite?: (stageId: string) => void | Promise<void>;
  acknowledgeHandoff?: () => void | Promise<void>;
}

/** Move the GUI to the right place for a pending operator action. */
export function navigateForPendingAction(
  pending: PendingAction,
  handlers: OperatorNavigateHandlers,
  opts: { openModal?: boolean } = {},
): void {
  void handlers.selectStage(pending.stageId);
  handlers.setActiveTab("pipeline");

  switch (pending.kind) {
    case "write_approval":
      handlers.setPipelineSubTab("files");
      if (opts.openModal) handlers.openActionModal();
      break;
    case "handoff":
      handlers.setPipelineSubTab("stage");
      handlers.closeActionModal();
      requestAnimationFrame(() => {
        document.getElementById("stage-handoff-panel")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
      break;
    case "stage_reuse":
      handlers.setPipelineSubTab("stage");
      requestAnimationFrame(() => {
        document.querySelector(".stage-reuse-section")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
      break;
    case "gate":
    case "blocked":
      handlers.setPipelineSubTab(
        pending.subTab === "story"
          ? "story"
          : pending.subTab === "timeline"
            ? "timeline"
            : pending.subTab === "profile"
              ? "profile"
              : "stage",
      );
      if (opts.openModal !== false) handlers.openActionModal();
      break;
    default:
      handlers.setPipelineSubTab(pending.subTab ?? "stage");
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
