import type { AppConfig, RunData } from "../types";
import { findNextRunnableStage } from "./preclean";
import {
  stageArtifactsFullyComplete,
  upstreamArtifactsReady,
  firstUpstreamBlocker,
} from "./stageOutputs";
import { gapFillSkipped } from "./stageVisibility";

/** Stages that need operator checkpoints — autopilot focuses but does not auto-run. */
export const MANUAL_CHECKPOINT_STAGES = new Set([
  "transcript_review",
  "g1_vo_pickup",
]);

const MANUAL_BLOCKING = new Set([
  "stage_reuse",
  "llm_gate",
  "transcript_review",
  "g1_vo_pickup",
  "gate",
]);

function firstTryEnabled(config?: AppConfig | null, run?: RunData): boolean {
  if (run?.journey?.first_try?.enabled === false) return false;
  if (config?.journey_ui && "first_try_mode" in config.journey_ui) {
    return Boolean((config.journey_ui as { first_try_mode?: boolean }).first_try_mode);
  }
  return run?.journey?.first_try?.enabled !== false;
}

export function isPipelineAutopilotEnabled(config?: AppConfig | null): boolean {
  if (config?.journey_ui?.enabled === false) return false;
  return config?.journey_ui?.auto_advance_pipeline !== false;
}

export function canAutoRunStage(stageId: string, run?: RunData, config?: AppConfig | null): boolean {
  if (MANUAL_CHECKPOINT_STAGES.has(stageId)) {
    if (!run || !firstTryEnabled(config, run)) return false;
    if (stageId === "transcript_review") {
      return run.journey?.blocking?.reason !== "transcript_review";
    }
    if (stageId === "g1_vo_pickup") {
      if (gapFillSkipped(run)) return true;
      return (run.g1_missing || []).length === 0;
    }
    return false;
  }
  if (run && !upstreamArtifactsReady(run.stages, stageId, run.meta)) return false;
  return true;
}

export function isPipelineComplete(run: RunData): boolean {
  const next = findNextRunnableStage(run.stages, run.meta);
  if (next) return false;

  const pending = run.stages.some(
    (s) =>
      s.stage_output_mode !== "optional_skipped" &&
      (s.status === "pending" ||
        s.status === "incomplete" ||
        s.status === "action_required" ||
        s.status === "awaiting_write_approval"),
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

/** True when autopilot must not start the next stage job (reuse, gates, etc.). */
export function autopilotBlocksAutoRun(run: RunData, config?: AppConfig | null): boolean {
  void config;
  const blocking = run.journey?.blocking ?? run.blocking;
  if (!blocking?.blocked) {
    if (run.job?.needs_stage_reuse) return true;
    if (run.job?.status === "gate" || run.job?.status === "needs_operator") return true;
    if (run.job?.status === "needs_clarification") return true;
    if (run.job?.status === "awaiting_write_approval" || run.job?.awaiting_write_approval) {
      return true;
    }
    if (Number(run.job?.sufficiency_blocking ?? 0) > 0) {
      return true;
    }
    return false;
  }

  const reason = blocking.reason || "";
  if (reason === "handoff_review" || reason === "llm_degraded_review") return false;
  return MANUAL_BLOCKING.has(reason);
}

/** @deprecated Use autopilotBlocksAutoRun — kept for existing imports. */
export function autopilotBlockedByRun(run: RunData): boolean {
  return autopilotBlocksAutoRun(run);
}

function autopilotBlocksNavigationFromStage(run: RunData, completedStageId: string): boolean {
  const blocking = run.journey?.blocking ?? run.blocking;
  if (!blocking?.blocked) {
    if (run.job?.status === "awaiting_write_approval" || run.job?.awaiting_write_approval) {
      const sid = run.job?.pending_write_stage || run.job?.stage;
      if (sid === completedStageId) return true;
    }
    return false;
  }

  if (blocking.stage_id === completedStageId && blocking.reason === "write_approval") {
    return true;
  }

  return false;
}

/** True when autopilot should select the next sidebar stage after a stage completes. */
export function shouldAutoNavigateFromStage(
  run: RunData,
  stageId: string | null,
  config?: AppConfig | null,
): boolean {
  if (config?.journey_ui?.enabled === false) return false;
  if (!stageId) return false;
  if (isPipelineComplete(run)) return false;

  const stage = run.stages.find((s) => s.id === stageId);
  if (!stage || stage.status !== "done") return false;
  if (!stageArtifactsFullyComplete(stage)) return false;

  if (autopilotBlocksNavigationFromStage(run, stageId)) return false;

  const next = findNextRunnableStage(run.stages, run.meta);
  if (next && firstUpstreamBlocker(run.stages, next.id, run.meta)) return false;
  if (next) return true;

  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.stage_id && blocking.stage_id !== stageId) {
    return true;
  }

  return false;
}

export function shouldAutoContinueFromStage(
  run: RunData,
  stageId: string | null,
  config?: AppConfig | null,
): boolean {
  if (!shouldAutoNavigateFromStage(run, stageId, config)) return false;
  if (autopilotBlocksAutoRun(run, config)) return false;

  const next = findNextRunnableStage(run.stages, run.meta);
  return Boolean(next);
}
