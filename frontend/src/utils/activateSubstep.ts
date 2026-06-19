import type { AppTab, GuidanceItem, PipelineSubTab, StageSubstep } from "../types";
import { guidanceItemToSubstep } from "./stageSubsteps";

export interface ActivateSubstepHandlers {
  selectStage: (id: string) => void | Promise<void>;
  setActiveTab: (tab: AppTab) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  openActionModal: () => void;
  closeActionModal: () => void;
  runNextStage: () => void | Promise<void>;
  approveWrite?: (stageId: string) => void | Promise<void>;
  acknowledgeHandoff?: () => void | Promise<void>;
  setActiveSubstepId?: (id: string | null) => void;
}

function scrollToSection(sectionId?: string): void {
  if (!sectionId || typeof document === "undefined") return;
  const scroll = () => {
    document.getElementById(sectionId)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(scroll);
  } else {
    scroll();
  }
}

function scrollToSelector(selector: string): void {
  if (typeof document === "undefined") return;
  const scroll = () => {
    document.querySelector(selector)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(scroll);
  } else {
    scroll();
  }
}

/** Move the GUI to the right place for a substep activation. */
export function activateSubstep(
  substep: StageSubstep,
  handlers: ActivateSubstepHandlers,
  opts: { openModal?: boolean; scrollSection?: boolean } = {},
): void {
  const openModal = opts.openModal ?? true;
  const scrollSection = opts.scrollSection ?? true;

  handlers.setActiveSubstepId?.(substep.id);
  void handlers.selectStage(substep.stageId);
  handlers.setActiveTab("pipeline");

  if (substep.targetSubTab) {
    handlers.setPipelineSubTab(substep.targetSubTab);
  }

  switch (substep.kind) {
    case "write_approval":
      if (substep.primaryLabel && handlers.approveWrite && !openModal) {
        void handlers.approveWrite(substep.stageId);
        return;
      }
      if (openModal) handlers.openActionModal();
      if (scrollSection) scrollToSection(substep.targetSection || "modal-write-approval");
      return;

    case "handoff":
      handlers.closeActionModal();
      if (scrollSection) scrollToSection("stage-handoff-panel");
      return;

    case "reuse":
      if (openModal) handlers.openActionModal();
      else scrollToSelector(".stage-reuse-section");
      if (scrollSection) scrollToSection(substep.targetSection || "modal-reuse");
      return;

    case "gate":
    case "blocked":
    case "checkpoint":
      if (openModal) handlers.openActionModal();
      if (scrollSection) scrollToSection(substep.targetSection || "modal-gates");
      return;

    case "profile":
      handlers.setPipelineSubTab("profile");
      return;

    case "story_board":
    case "milestone":
      handlers.setPipelineSubTab("story");
      return;

    case "run":
      void handlers.runNextStage();
      return;

    case "start":
      handlers.setActiveTab("start");
      return;

    case "optional":
      handlers.setPipelineSubTab("stage");
      if (openModal) handlers.openActionModal();
      return;

    default:
      if (substep.targetSection && openModal) {
        handlers.openActionModal();
        if (scrollSection) scrollToSection(substep.targetSection);
      } else if (openModal) {
        handlers.openActionModal();
      }
  }
}

export function activateGuidanceItem(
  item: GuidanceItem,
  stageId: string,
  handlers: ActivateSubstepHandlers,
  opts?: { openModal?: boolean; scrollSection?: boolean },
): void {
  activateSubstep(guidanceItemToSubstep(item, stageId), handlers, opts);
}
