import type { RunMeta, StageInfo, StageStatus } from "../types";

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
      prompt: "Clean source interview background noise before ingest?",
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
