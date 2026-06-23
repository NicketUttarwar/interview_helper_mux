import { describe, expect, it } from "vitest";
import { substepShouldOpenModal } from "./substepModal";
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

describe("substepShouldOpenModal", () => {
  it("opens modal for gate and checkpoint kinds", () => {
    expect(substepShouldOpenModal(sub({ kind: "gate", stageId: "g2_flow_select" }))).toBe(true);
    expect(substepShouldOpenModal(sub({ kind: "checkpoint", stageId: "audio_preclean" }))).toBe(true);
    expect(substepShouldOpenModal(sub({ kind: "write_approval", stageId: "ingest" }))).toBe(true);
  });

  it("does not open modal for profile navigation", () => {
    expect(substepShouldOpenModal(sub({ kind: "profile", stageId: "analysis_profile" }))).toBe(false);
  });

  it("opens modal for optional preclean review but not skip", () => {
    expect(
      substepShouldOpenModal(
        sub({ kind: "optional", id: "optional:review", stageId: "g1_vo_pickup" }),
      ),
    ).toBe(true);
    expect(
      substepShouldOpenModal(
        sub({ kind: "optional", id: "optional:skip", stageId: "audio_preclean" }),
      ),
    ).toBe(false);
  });
});
