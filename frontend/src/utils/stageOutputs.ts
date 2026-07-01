import type { StageInfo } from "../types";

/** True when every non-skipped expected output is committed/complete on disk. */
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
  if (stage.status === "done" && !stageHasCommittedOutputs(stage)) {
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
    if (s.status === "skipped") continue;
    if (s.status === "done" && !stageHasCommittedOutputs(s)) return false;
    if (s.status === "incomplete") return false;
  }
  return true;
}
