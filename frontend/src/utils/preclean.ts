import type { StageInfo, StageStatus } from "../types";

export function resolvePrecleanOffer(stage: StageInfo): {
  checkpoint: string;
  scope: string;
  prompt: string;
} | null {
  if (stage.id === "audio_preclean") {
    return {
      checkpoint: "before_ingest",
      scope: "full_source",
      prompt: "Clean source interview background noise before ingest?",
    };
  }
  if (stage.id === "transcript_review" && stage.status === "done") {
    return {
      checkpoint: "after_g0",
      scope: "full_source",
      prompt:
        "Re-clean full source if low-confidence transcript errors seem noise-related?",
    };
  }
  if (stage.id === "analysis_profile" || stage.id === "segment_classification") {
    return {
      checkpoint: "after_profile_or_segmentation",
      scope: "full_source",
      prompt: "Clean source audio before re-running analysis from ingest?",
    };
  }
  if (stage.id === "g1_vo_pickup" && stage.status === "done") {
    return {
      checkpoint: "g1_vo_pickup",
      scope: "vo_pickup",
      prompt: "Remove background noise from new pickup recordings?",
    };
  }
  if (
    stage.id === "mix_flow1" ||
    stage.id === "mix_flow2" ||
    stage.id === "mux_flow1" ||
    stage.id === "mux_flow2"
  ) {
    return {
      checkpoint: "before_flow_mix",
      scope: "normalized_rebuild",
      prompt: "Clean normalized interview audio before final assembly/mix?",
    };
  }
  if (stage.id === "assembly_preview") {
    return {
      checkpoint: "before_sfx_spend",
      scope: "full_source",
      prompt: "Clean source before ElevenLabs SFX spend?",
    };
  }
  if (stage.id === "master_flow1" || stage.id === "master_flow2") {
    return {
      checkpoint: "before_master_export",
      scope: "normalized_rebuild",
      prompt: "Last chance: pre-clean before master export?",
    };
  }
  return null;
}

export function findActiveStage(stages: StageInfo[]): StageInfo | undefined {
  return (
    stages.find((s) => s.status === "action_required") ||
    stages.find((s) => s.status === "pending" && s.phase !== "gate")
  );
}

export function findNextRunnableStage(stages: StageInfo[]): StageInfo | undefined {
  for (const s of stages) {
    if (s.status === "action_required") return s;
    if (s.status === "pending" && s.phase !== "gate") return s;
  }
  return undefined;
}

export function hasActionRequiredStage(stages: StageInfo[]): boolean {
  return stages.some((s) => s.status === "action_required");
}

export function providersForExecute(
  body: { mode: string; stage?: string },
  stages: StageInfo[],
): string[] {
  if (body.mode === "stage" && body.stage) {
    const s = stages.find((x) => x.id === body.stage);
    return s?.api_providers || [];
  }
  if (body.mode === "analysis") {
    const set = new Set<string>();
    for (const s of stages) {
      if (s.phase === "analysis" && s.status === "pending" && s.api_providers) {
        s.api_providers.forEach((p) => set.add(p));
      }
    }
    return [...set];
  }
  const flowPhase =
    body.mode === "flow1"
      ? "flow1"
      : body.mode === "flow2"
        ? "flow2"
        : body.mode === "flow3"
          ? "flow3"
          : null;
  if (flowPhase) {
    const set = new Set<string>();
    for (const s of stages) {
      if (s.phase === flowPhase && s.status === "pending" && s.api_providers) {
        s.api_providers.forEach((p) => set.add(p));
      }
    }
    return [...set];
  }
  return [];
}

export function stageDotClass(status: StageStatus): string {
  if (status === "done") return "done";
  if (status === "action_required") return "action_required";
  if (status === "locked") return "locked";
  return "pending";
}
