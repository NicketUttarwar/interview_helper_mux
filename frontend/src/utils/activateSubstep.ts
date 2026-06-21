import type { AppTab, GuidanceItem, LogStreamTab, PipelineSubTab, StageSubstep } from "../types";
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
  setActivityLogCollapsed?: (collapsed: boolean) => void;
  setActivityLogTab?: (tab: LogStreamTab) => void;
  showToast?: (msg: string, level?: "info" | "error" | "warning") => void;
  skipOptionalStage?: (stageId: string) => void | Promise<void>;
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

/** Move the GUI to the right place for a substep activation (inline only). */
export function activateSubstep(
  substep: StageSubstep,
  handlers: ActivateSubstepHandlers,
  opts: { openModal?: boolean; scrollSection?: boolean } = {},
): void {
  const scrollSection = opts.scrollSection ?? true;

  handlers.setActiveSubstepId?.(substep.id);
  void handlers.selectStage(substep.stageId);
  handlers.setActiveTab("pipeline");

  if (substep.targetSubTab) {
    handlers.setPipelineSubTab(substep.targetSubTab);
  }

  switch (substep.kind) {
    case "write_approval":
      if (scrollSection) scrollToSection("write-approval-panel");
      return;

    case "handoff":
      if (scrollSection) scrollToSection("stage-handoff-panel");
      return;

    case "reuse":
      if (scrollSection) scrollToSelector(".stage-reuse-section");
      return;

    case "gate":
    case "blocked":
    case "checkpoint":
      if (scrollSection) scrollToSection("stage-gate-panel");
      if (substep.id.includes("preclean")) {
        scrollToSelector(".preclean-offer-card");
      }
      return;

    case "profile":
      handlers.setPipelineSubTab("profile");
      return;

    case "story_board":
    case "milestone":
      handlers.setPipelineSubTab("story");
      return;

    case "run":
      if (substep.status === "running") {
        handlers.setActivityLogTab?.("live");
        handlers.setActivityLogCollapsed?.(false);
        handlers.showToast?.(
          "This step is running — watch the activity log below.",
        );
        return;
      }
      return;

    case "start":
      handlers.setActiveTab("start");
      return;

    case "optional":
      if (substep.id === "optional:skip" && handlers.skipOptionalStage) {
        void handlers.skipOptionalStage(substep.stageId);
        return;
      }
      handlers.setPipelineSubTab("stage");
      scrollToSelector(".preclean-offer-card");
      return;

    default:
      if (substep.targetSection && scrollSection) {
        scrollToSection(substep.targetSection);
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
