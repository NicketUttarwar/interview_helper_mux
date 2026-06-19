import { describe, expect, it, vi } from "vitest";
import { activateSubstep } from "./activateSubstep";
import type { StageSubstep } from "../types";

function sub(partial: Partial<StageSubstep> & Pick<StageSubstep, "kind" | "stageId">): StageSubstep {
  return {
    id: partial.id ?? partial.kind,
    label: partial.label ?? partial.kind,
    status: partial.status ?? "todo",
    source: partial.source ?? "attention",
    ...partial,
  };
}

describe("activateSubstep", () => {
  it("opens modal and targets write approval section", () => {
    const openActionModal = vi.fn();
    const setPipelineSubTab = vi.fn();
    const selectStage = vi.fn();
    activateSubstep(
      sub({
        kind: "write_approval",
        stageId: "ingest",
        targetSection: "modal-write-approval",
        targetSubTab: "files",
      }),
      {
        selectStage,
        setActiveTab: vi.fn(),
        setPipelineSubTab,
        openActionModal,
        closeActionModal: vi.fn(),
        runNextStage: vi.fn(),
      },
      { scrollSection: false, openModal: true },
    );
    expect(selectStage).toHaveBeenCalledWith("ingest");
    expect(setPipelineSubTab).toHaveBeenCalledWith("files");
    expect(openActionModal).toHaveBeenCalled();
  });

  it("routes profile to profile sub-tab", () => {
    const setPipelineSubTab = vi.fn();
    activateSubstep(
      sub({ kind: "profile", stageId: "analysis_profile" }),
      {
        selectStage: vi.fn(),
        setActiveTab: vi.fn(),
        setPipelineSubTab,
        openActionModal: vi.fn(),
        closeActionModal: vi.fn(),
        runNextStage: vi.fn(),
      },
      { openModal: false },
    );
    expect(setPipelineSubTab).toHaveBeenCalledWith("profile");
  });

  it("calls runNextStage for run kind", () => {
    const runNextStage = vi.fn();
    activateSubstep(
      sub({ kind: "run", stageId: "ingest" }),
      {
        selectStage: vi.fn(),
        setActiveTab: vi.fn(),
        setPipelineSubTab: vi.fn(),
        openActionModal: vi.fn(),
        closeActionModal: vi.fn(),
        runNextStage,
      },
    );
    expect(runNextStage).toHaveBeenCalled();
  });

  it("inline write approval scrolls to panel without opening modal", () => {
    const openActionModal = vi.fn();
    const closeActionModal = vi.fn();
    const scrollIntoView = vi.fn();
    vi.stubGlobal(
      "document",
      {
        getElementById: vi.fn((id: string) =>
          id === "write-approval-panel" ? { scrollIntoView } : null,
        ),
        querySelector: vi.fn(),
      } as unknown as Document,
    );
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });

    activateSubstep(
      sub({
        kind: "write_approval",
        stageId: "ingest",
        targetSection: "modal-write-approval",
        targetSubTab: "files",
      }),
      {
        selectStage: vi.fn(),
        setActiveTab: vi.fn(),
        setPipelineSubTab: vi.fn(),
        openActionModal,
        closeActionModal,
        runNextStage: vi.fn(),
      },
      { openModal: false },
    );

    expect(openActionModal).not.toHaveBeenCalled();
    expect(closeActionModal).toHaveBeenCalled();
    expect(scrollIntoView).toHaveBeenCalled();

    vi.unstubAllGlobals();
  });
});
