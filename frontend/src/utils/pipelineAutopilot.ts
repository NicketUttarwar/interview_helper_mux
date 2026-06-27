import type { AppConfig, RunData } from "../types";
import { findHandoffStage } from "./checkpoint";
import { findNextRunnableStage } from "./preclean";
import { pendingWriteInfo } from "./writeApproval";

/** Stages that need operator checkpoints — autopilot focuses but does not auto-run. */
export const MANUAL_CHECKPOINT_STAGES = new Set([
  "transcript_review",
  "disfluency_review",
  "g1_vo_pickup",
  "g2_flow_select",
  "analysis_profile",
]);

/** Blocking reasons that stop autopilot until the operator acts. */
const MANUAL_BLOCKING_REASONS = new Set([
  "stage_reuse",
  "write_approval",
  "llm_gate",
  "transcript_review",
  "disfluency_review",
  "g1_vo_pickup",
  "g2_flow_select",
  "analysis_profile",
  "gate",
]);

export function isPipelineAutopilotEnabled(config?: AppConfig | null): boolean {
  if (config?.journey_ui?.enabled === false) return false;
  return config?.journey_ui?.auto_advance_pipeline !== false;
}

export function canAutoRunStage(stageId: string): boolean {
  return !MANUAL_CHECKPOINT_STAGES.has(stageId);
}

export function isPipelineComplete(run: RunData): boolean {
  const next = findNextRunnableStage(run.stages, run.meta);
  if (next) return false;

  const pending = run.stages.some(
    (s) =>
      s.status === "pending" ||
      s.status === "action_required" ||
      s.status === "awaiting_write_approval",
  );
  if (pending) return false;

  const kind = run.journey?.deliverable?.kind;
  if (kind && kind !== "none") return true;

  return run.journey?.phase === "ship";
}

export function resolveFinalOutputRelativePath(run: RunData): string | null {
  const paths = run.journey?.deliverable?.paths;
  if (!paths) return null;
  return paths.master || paths.description || paths.preview || null;
}

export function resolveFinalOutputAbsolutePath(run: RunData): string | null {
  const rel = resolveFinalOutputRelativePath(run);
  const base = run.working_dir?.replace(/\/$/, "");
  if (!rel || !base) return rel;
  return `${base}/${rel}`;
}

export function autopilotBlockedByRun(run: RunData): boolean {
  const write = pendingWriteInfo(run);
  if (write?.paths.length) return true;

  const blocking = run.journey?.blocking ?? run.blocking;
  if (!blocking?.blocked) {
    if (run.job?.needs_stage_reuse) return true;
    if (run.job?.status === "gate" || run.job?.status === "needs_operator") return true;
    if (run.job?.status === "awaiting_write_approval" || run.job?.awaiting_write_approval) {
      return true;
    }
    return false;
  }

  const reason = blocking.reason || "";
  if (reason === "handoff_review" || reason === "llm_degraded_review") return false;
  return MANUAL_BLOCKING_REASONS.has(reason);
}

export function shouldAutoContinueFromStage(
  run: RunData,
  stageId: string | null,
  config?: AppConfig | null,
): boolean {
  if (!stageId || !isPipelineAutopilotEnabled(config)) return false;
  if (isPipelineComplete(run)) return false;
  if (autopilotBlockedByRun(run)) return false;

  const stage = run.stages.find((s) => s.id === stageId);
  if (!stage || stage.status !== "done") return false;

  const handoff = findHandoffStage(run);
  if (handoff?.id === stageId) return true;

  const next = findNextRunnableStage(run.stages, run.meta);
  return Boolean(next);
}
