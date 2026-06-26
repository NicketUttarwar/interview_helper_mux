import type { RunMeta, StageInfo, StageStatus } from "../types";

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

/** True when operator dismissed optional pre-clean for this stage's checkpoint. */
export function isOptionalStageSkipped(
  stage: StageInfo,
  meta?: RunMeta | null,
): boolean {
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

export function findNextRunnableStage(
  stages: StageInfo[],
  _meta?: RunMeta | null,
): StageInfo | undefined {
  for (const s of stages) {
    if (s.status === "awaiting_write_approval") return s;
  }
  for (const s of stages) {
    if (s.status === "action_required") return s;
  }
  for (const s of stages) {
    if (s.status === "pending" && s.phase !== "gate") return s;
  }
  return undefined;
}

export function hasActionRequiredStage(stages: StageInfo[]): boolean {
  return stages.some((s) => s.status === "action_required");
}

export function stageDotClass(status: StageStatus): string {
  if (status === "done") return "done";
  if (status === "action_required") return "action_required";
  if (status === "awaiting_write_approval") return "action_required";
  if (status === "locked") return "locked";
  return "pending";
}
