import type { StageInfo } from "../types";

/** True when every required artifact is fully committed (not staged/partial/pending). */
export function stageArtifactsFullyComplete(stage: StageInfo): boolean {
  const outputs = stage.outputs_view;
  if (outputs?.length) {
    return outputs.every((row) => {
      if (row.phase === "n_a" || row.phase === "skipped") return true;
      return row.status === "complete" || row.phase === "committed";
    });
  }
  const statusMap = stage.artifacts_status || {};
  const lifecycle = stage.artifacts_lifecycle || {};
  const paths = stage.artifacts?.filter((p) => p && !p.endsWith("/")) || [];
  if (!paths.length) return true;
  return paths.every((p) => {
    const phase = lifecycle[p];
    if (phase === "n_a" || phase === "skipped") return true;
    return statusMap[p] === "complete";
  });
}

/** True when outputs are present for operator review (staged counts during write approval). */
export function stageHasCommittedOutputs(stage: StageInfo): boolean {
  const outputs = stage.outputs_view;
  if (outputs?.length) {
    return outputs.every((row) => {
      if (row.phase === "n_a" || row.phase === "skipped") return true;
      if (row.phase === "staged") return true;
      return row.status === "complete" || row.phase === "committed";
    });
  }
  const statusMap = stage.artifacts_status || {};
  const lifecycle = stage.artifacts_lifecycle || {};
  const paths = stage.artifacts?.filter((p) => p && !p.endsWith("/")) || [];
  if (!paths.length) return true;
  return paths.every((p) => {
    const phase = lifecycle[p];
    if (phase === "n_a" || phase === "skipped") return true;
    return statusMap[p] === "complete" || statusMap[p] === "staged";
  });
}

export function stageIncompleteReason(stage: StageInfo): string | null {
  if (stage.status !== "incomplete" && stage.status !== "done") return null;
  const ext = (stage as StageInfo & { incomplete_reason?: string }).incomplete_reason;
  if (ext) return ext;
  if (
    (stage.status === "done" || stage.status === "incomplete") &&
    !stageArtifactsFullyComplete(stage)
  ) {
    const pending = Object.entries(stage.artifacts_status || {}).find(
      ([, st]) => st === "pending" || st === "partial",
    );
    if (pending) return `${pending[0]} is ${pending[1]}`;
    return "Required output files are missing or incomplete";
  }
  return null;
}

/** Upstream artifact complete check for autopilot / continue guards. */
export function upstreamArtifactsReady(
  stages: StageInfo[],
  targetStageId: string,
): boolean {
  const idx = stages.findIndex((s) => s.id === targetStageId);
  if (idx <= 0) return true;
  for (let i = 0; i < idx; i++) {
    const s = stages[i];
    if (s.status === "incomplete") return false;
    if (s.status !== "done") return false;
    if (!stageArtifactsFullyComplete(s)) return false;
  }
  return true;
}

/** First upstream stage that blocks progression to targetStageId, if any. */
export function firstUpstreamBlocker(
  stages: StageInfo[],
  targetStageId: string,
): StageInfo | null {
  const idx = stages.findIndex((s) => s.id === targetStageId);
  if (idx <= 0) return null;
  for (let i = 0; i < idx; i++) {
    const s = stages[i];
    if (s.status === "incomplete") return s;
    if (s.status !== "done") return s;
    if (!stageArtifactsFullyComplete(s)) return s;
  }
  return null;
}
