import type { RunMeta, StageInfo, StageStatus } from "../types";
import { firstUpstreamBlocker } from "./stageOutputs";
import { isStageHidden } from "./stageVisibility";

export function precleanDismissedAtCheckpoint(
  preclean: RunMeta["audio_preclean"] | undefined,
  checkpoint: string,
): boolean {
  const decisions = preclean?.decisions;
  if (!Array.isArray(decisions)) return false;
  return decisions.some(
    (d) => d.checkpoint === checkpoint && d.action === "dismiss",
  );
}

export function precleanOfferSettled(
  preclean: RunMeta["audio_preclean"] | undefined,
  checkpoint: string,
): boolean {
  const decisions = preclean?.decisions;
  if (!Array.isArray(decisions)) return false;
  return decisions.some(
    (d) =>
      d.checkpoint === checkpoint &&
      (d.action === "dismiss" || d.action === "accept"),
  );
}

export function resolvePrecleanOffer(
  stage: StageInfo,
  meta?: RunMeta | null,
): {
  checkpoint: string;
  scope: string;
  prompt: string;
} | null {
  let offer: {
    checkpoint: string;
    scope: string;
    prompt: string;
  } | null = null;

  if (stage.id === "audio_preclean") {
    offer = {
      checkpoint: "before_ingest",
      scope: "full_source",
      prompt: "Clean source interview background noise before ingest.",
    };
  } else if (stage.id === "g1_vo_pickup" && stage.status === "done") {
    offer = {
      checkpoint: "g1_vo_pickup",
      scope: "vo_pickup",
      prompt: "Remove background noise from new pickup recordings?",
    };
  }

  if (!offer) return null;
  if (precleanOfferSettled(meta?.audio_preclean, offer.checkpoint)) return null;
  return offer;
}

/** True when optional/N/A stage is skipped (preclean dismiss or backend optional_skipped). */
export function isOptionalStageSkipped(
  stage: StageInfo,
  meta?: RunMeta | null,
): boolean {
  if (stage.stage_output_mode === "optional_skipped") return true;
  if (stage.id === "audio_preclean") {
    return precleanDismissedAtCheckpoint(meta?.audio_preclean, "before_ingest");
  }
  if (stage.id === "g1_vo_pickup") {
    return precleanDismissedAtCheckpoint(meta?.audio_preclean, "g1_vo_pickup");
  }
  return false;
}

export function getOptionalSkipLabel(stage: StageInfo): string {
  return "Skip optional step";
}

export function findActiveStage(
  stages: StageInfo[],
  meta?: RunMeta | null,
): StageInfo | undefined {
  return findNextRunnableStage(stages, meta);
}

/** Incomplete is actionable only when N/A-skip is false and upstream stages are ready. */
export function isActionableIncomplete(
  stages: StageInfo[],
  stage: StageInfo,
  meta?: RunMeta | null,
): boolean {
  if (stage.status !== "incomplete") return false;
  if (stage.stage_output_mode === "optional_skipped") return false;
  if (firstUpstreamBlocker(stages, stage.id, meta)) return false;
  return true;
}

export function findNextRunnableStage(
  stages: StageInfo[],
  meta?: RunMeta | null,
): StageInfo | undefined {
  for (const s of stages) {
    if (isStageHidden(s)) continue;
    if (s.status === "awaiting_write_approval") return s;
  }
  for (const s of stages) {
    if (isStageHidden(s)) continue;
    if (s.status === "action_required") return s;
  }
  for (const s of stages) {
    if (isStageHidden(s)) continue;
    if (isActionableIncomplete(stages, s, meta)) return s;
  }
  for (const s of stages) {
    if (isStageHidden(s)) continue;
    if (s.status === "pending" && s.phase !== "gate") {
      if (isOptionalStageSkipped(s, meta)) continue;
      if (firstUpstreamBlocker(stages, s.id, meta)) continue;
      return s;
    }
  }
  return undefined;
}

export function hasActionRequiredStage(stages: StageInfo[]): boolean {
  return stages.some((s) => s.status === "action_required");
}

export function stageDotClass(status: StageStatus): string {
  if (status === "done") return "done";
  if (status === "incomplete") return "action_required";
  if (status === "action_required") return "action_required";
  if (status === "awaiting_write_approval") return "action_required";
  if (status === "locked") return "locked";
  return "pending";
}
