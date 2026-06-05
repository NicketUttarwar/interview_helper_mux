import type { LogEntry, RunData, StageInfo } from "../types";
import { parseLogDetail } from "./index";

const CUSTOM_RUN_ARTIFACT_PREFIXES = [
  "understanding/",
  "segments/",
  "flow_1_master/",
  "flow_2_highlights/",
  "flow_3_description/",
  "sound_design/",
] as const;

const NON_CUSTOM_RUN_EXACT = new Set([
  "ingest/checksums.json",
  "transcript/corrections.json",
  "transcript/review_queue.json",
  "segments/nle_edits.json",
]);

export function isCustomRunArtifactPath(path: string): boolean {
  if (!path || path.endsWith("/") || NON_CUSTOM_RUN_EXACT.has(path)) return false;
  return CUSTOM_RUN_ARTIFACT_PREFIXES.some((prefix) => path.startsWith(prefix));
}

export function filterCustomRunHandoffPaths(paths: string[]): string[] {
  return paths.filter(isCustomRunArtifactPath);
}

function filterCompleteHandoffPaths(stage: StageInfo, paths: string[]): string[] {
  const custom = filterCustomRunHandoffPaths(paths);
  if (stage.handoff_paths?.length) {
    const serverSet = new Set(stage.handoff_paths);
    return custom.filter((p) => serverSet.has(p));
  }
  const statusMap = stage.artifacts_status || {};
  return custom.filter((p) => statusMap[p] === "complete");
}

export function getHandoffPathsLocal(
  stage: StageInfo,
  logTail?: LogEntry[],
): string[] {
  if (stage.handoff_paths?.length) {
    return filterCustomRunHandoffPaths(stage.handoff_paths);
  }
  for (let i = (logTail || []).length - 1; i >= 0; i--) {
    const e = logTail![i];
    if (e.stage !== stage.id) continue;
    const d = parseLogDetail(e.detail);
    if (Array.isArray(d?.handoff) && d.handoff.length) {
      return filterCompleteHandoffPaths(stage, d.handoff as string[]);
    }
  }
  return filterCompleteHandoffPaths(
    stage,
    [...(stage.artifacts_present || []), ...(stage.artifacts || [])].filter(
      (p, i, arr) => Boolean(p) && !p.endsWith("/") && arr.indexOf(p) === i,
    ),
  );
}

/** Stage id the operator should focus on for checkpoints, gates, handoffs, or job pause. */
export function findPendingFocusStage(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): string | null {
  if (!run) return null;
  const actionStage = run.stages.find((s) => s.status === "action_required");
  if (actionStage) return actionStage.id;
  if (run.job?.status === "gate" && run.job.stage) return run.job.stage;
  if (run.job?.needs_stage_reuse && run.job.stage) return run.job.stage;
  if (
    run.job?.status === "needs_operator" &&
    !isApiConsentJobPending(run, grants) &&
    run.job.stage
  ) {
    return run.job.stage;
  }
  const handoff = findHandoffStage(run);
  if (handoff) return handoff.id;
  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.stage_id) return blocking.stage_id;
  return null;
}

export function continueHintForStage(stageId: string): string {
  switch (stageId) {
    case "transcript_review":
      return "Complete transcript review in the panel above (save clips or use Complete review).";
    case "g1_vo_pickup":
      return "Record or upload every pickup line listed above.";
    case "analysis_profile":
      return "Review the AI-generated profile above, then mark verified when it matches your intent.";
    case "g2_flow_select":
      return "Select your deliverable flow below (or use your planned choice).";
    case "elevenlabs_prompt_craft":
      return "Approve ElevenLabs prompts and complete listen checks above.";
    case "elevenlabs_sfx_flow1":
    case "elevenlabs_sfx_flow2":
      return "Listen to outputs and pass or fail the sound check above.";
    default:
      return "Complete the required steps above before continuing.";
  }
}

export function findHandoffStage(run: RunData | null): StageInfo | null {
  if (!run) return null;
  for (const s of run.stages) {
    if (s.status !== "done") continue;
    const paths = getHandoffPathsLocal(s, run.log_tail);
    if (paths.length > 0 && !run.handoff_ack?.[s.id]) return s;
  }
  return null;
}

/** True when job is stopped for API consent and at least one provider is still ungranted. */
export function isApiConsentJobPending(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): boolean {
  const job = run?.job;
  if (!job || job.status !== "needs_operator") return false;
  const missing = job.missing_api_providers;
  const apiRelated =
    job.message?.includes("API consent") || Boolean(missing?.length);
  if (!apiRelated) return true;
  return (missing || []).some((id) => !grants[id]);
}

export function countPendingActions(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): number {
  if (!run) return 0;
  let n = 0;
  if (run.job?.status === "gate") n += 1;
  else if (run.job?.status === "needs_operator" && isApiConsentJobPending(run, grants)) {
    n += 1;
  }
  n += run.stages.filter((s) => s.status === "action_required").length;
  for (const s of run.stages) {
    if (s.status !== "done") continue;
    const paths = getHandoffPathsLocal(s, run.log_tail);
    if (paths.length && !run.handoff_ack?.[s.id]) n += 1;
  }
  return n;
}

export function actionSummaryText(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): string | null {
  if (!run) return null;
  const job = run.job;
  const actionStage = run.stages.find((s) => s.status === "action_required");
  if (job?.status === "gate") {
    return job.message || "Action required before the pipeline can continue.";
  }
  if (job?.status === "needs_operator" && isApiConsentJobPending(run, grants)) {
    return job.message || "Action required before the pipeline can continue.";
  }
  if (actionStage) {
    return `${actionStage.title} — complete the required steps.`;
  }
  const handoffStage = findHandoffStage(run);
  if (handoffStage) {
    return `Review AI outputs from ${handoffStage.title}.`;
  }
  return null;
}

export function checkpointContinueEnabled(
  run: RunData,
  stage: StageInfo,
  grants: Record<string, boolean> = {},
): boolean {
  if (isApiConsentJobPending(run, grants)) {
    return false;
  }
  if (stage.status === "action_required") {
    if (stage.id === "g1_vo_pickup") return Boolean(run.g1_clear);
    if (stage.id === "analysis_profile") {
      return Boolean(run.profile_verified) && Boolean(run.profile_ready_for_review);
    }
    return false;
  }
  if (stage.status === "done") {
    const paths = getHandoffPathsLocal(stage, run.log_tail);
    return paths.length > 0 && !run.handoff_ack?.[stage.id];
  }
  return false;
}

export function stageTitleForId(
  stages: StageInfo[] | undefined,
  stageId: string | undefined | null,
): string | null {
  if (!stageId || !stages) return null;
  return stages.find((s) => s.id === stageId)?.title ?? stageId;
}
