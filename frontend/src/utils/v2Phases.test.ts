import { describe, expect, it } from "vitest";
import { V2_PHASES, phaseForStage, phaseStageIds, phasesForId } from "./v2Phases";

describe("v2 phase mirror", () => {
  it("covers all 72 pipeline stages exactly once", () => {
    const stages = V2_PHASES.flatMap((p) => p.stages);
    expect(stages).toHaveLength(72);
    expect(new Set(stages).size).toBe(72);
  });

  it("includes the stages the mirror had drifted away from", () => {
    const stages = new Set(V2_PHASES.flatMap((p) => p.stages));
    for (const stage of [
      "low_conf_island_scan",
      "connector_fuse_pass",
      "audio_probe_build",
      "framing_posture_decide",
      "selection_order_sanitize",
      "gap_report_sanitize",
      "air_contract_sanitize",
    ]) {
      expect(stages.has(stage)).toBe(true);
    }
  });

  it("adopts the previously orphaned stages into the phases Python assigns", () => {
    expect(phaseForStage("audio_probe_build")?.id).toBe("prepare");
    expect(phaseForStage("framing_posture_decide")?.id).toBe("understand-b");
    for (const stage of [
      "selection_order_sanitize",
      "gap_report_sanitize",
      "air_contract_sanitize",
    ]) {
      expect(phaseForStage(stage)?.id).toBe("plan_rank");
    }
  });

  it("resolves the pre-split understand id through legacyId", () => {
    expect(phasesForId("understand").map((p) => p.id)).toEqual([
      "understand-a",
      "understand-b",
      "understand-c",
    ]);
    const legacy = phaseStageIds("understand");
    expect(legacy).toEqual([
      ...phaseStageIds("understand-a"),
      ...phaseStageIds("understand-b"),
      ...phaseStageIds("understand-c"),
    ]);
    expect(legacy[0]).toBe("source_acoustic_profile");
    expect(legacy[legacy.length - 1]).toBe("mastering_plan_synthesize");
  });

  it("prefers an exact id over a legacy id and returns nothing for unknown ids", () => {
    expect(phasesForId("understand-b").map((p) => p.id)).toEqual(["understand-b"]);
    expect(phasesForId("nope")).toEqual([]);
    expect(phaseStageIds("nope")).toEqual([]);
  });

  it("resolves gates to their phase", () => {
    expect(phaseForStage("transcript_review")?.id).toBe("fix_transcript");
    expect(phaseForStage("g1_vo_pickup")?.id).toBe("fill_gaps");
    expect(phaseForStage("g_publish")?.id).toBe("ship");
  });
});
