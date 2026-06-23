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
  it("routes write approval to files sub-tab and scroll target", () => {
    const setPipelineSubTab = vi.fn();
    const selectStage = vi.fn();
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
        targetSubTab: "files",
      }),
      {
        selectStage,
        setActiveTab: vi.fn(),
        setPipelineSubTab,
        openActionModal: vi.fn(),
        closeActionModal: vi.fn(),
        runNextStage: vi.fn(),
      },
    );
    expect(selectStage).toHaveBeenCalledWith("ingest");
    expect(setPipelineSubTab).toHaveBeenCalledWith("files");
    expect(scrollIntoView).toHaveBeenCalled();
    vi.unstubAllGlobals();
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
    );
    expect(setPipelineSubTab).toHaveBeenCalledWith("profile");
  });

  it("does not auto-run for run kind todo", () => {
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
    expect(runNextStage).not.toHaveBeenCalled();
  });

  it("scrolls to gate panel and opens modal for gate substeps", () => {
    const scrollIntoView = vi.fn();
    const openActionModal = vi.fn();
    vi.stubGlobal(
      "document",
      {
        getElementById: vi.fn((id: string) =>
          id === "stage-gate-panel" ? { scrollIntoView } : null,
        ),
        querySelector: vi.fn(),
      } as unknown as Document,
    );
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });

    activateSubstep(
      sub({ kind: "gate", stageId: "transcript_review" }),
      {
        selectStage: vi.fn(),
        setActiveTab: vi.fn(),
        setPipelineSubTab: vi.fn(),
        openActionModal,
        closeActionModal: vi.fn(),
        runNextStage: vi.fn(),
      },
    );
    expect(scrollIntoView).toHaveBeenCalled();
    expect(openActionModal).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("runs stage for run kind todo substeps", () => {
    const executeStage = vi.fn();
    activateSubstep(
      sub({ kind: "run", stageId: "ingest", status: "todo" }),
      {
        selectStage: vi.fn(),
        setActiveTab: vi.fn(),
        setPipelineSubTab: vi.fn(),
        openActionModal: vi.fn(),
        closeActionModal: vi.fn(),
        runNextStage: vi.fn(),
        executeStage,
      },
    );
    expect(executeStage).toHaveBeenCalledWith("ingest");
  });
});
