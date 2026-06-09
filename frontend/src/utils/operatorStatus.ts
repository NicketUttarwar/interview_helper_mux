import type { JobState, RunData, StageInfo } from "../types";
import { findHandoffStage } from "./checkpoint";

export interface JobStatusContext {
  isRunning: boolean;
  awaitingWriteApproval: boolean;
  needsStageReuse: boolean;
  needsGate: boolean;
  actionRequiredStage: StageInfo | undefined;
  handoffStage: StageInfo | null;
}

export function resolveJobStatusContext(
  run: RunData,
  jobRunning: boolean,
): JobStatusContext {
  const job = run.job;
  const isRunning =
    jobRunning ||
    job?.status === "running" ||
    job?.status === "running_with_warnings";
  const awaitingWriteApproval = Boolean(
    job?.status === "awaiting_write_approval" || job?.awaiting_write_approval,
  );
  const needsStageReuse = Boolean(job?.needs_stage_reuse && job.stage);
  const actionRequiredStage = run.stages.find((s) => s.status === "action_required");
  const needsGate = Boolean(job?.status === "gate" || actionRequiredStage);
  return {
    isRunning,
    awaitingWriteApproval,
    needsStageReuse,
    needsGate,
    actionRequiredStage,
    handoffStage: findHandoffStage(run),
  };
}

export function writeApprovalStatusLine(
  run: RunData,
  job: JobState | undefined,
): string {
  const sid = job?.pending_write_stage || job?.stage;
  const stage = sid ? run.stages.find((s) => s.id === sid) : null;
  return stage
    ? `${stage.title} — review outputs before saving`
    : "Review stage outputs before saving";
}

export function reuseStatusLine(run: RunData, job: JobState | undefined): string {
  const stage = job?.stage ? run.stages.find((s) => s.id === job.stage) : null;
  return stage
    ? `${stage.title} — reuse from a previous execution?`
    : "Choose reuse or run fresh";
}

export function gateStatusLine(
  run: RunData,
  job: JobState | undefined,
  actionRequiredStage: StageInfo | undefined,
): string {
  const gate =
    actionRequiredStage || run.stages.find((s) => s.id === job?.stage);
  return gate
    ? `${gate.title} needs your input`
    : job?.message || "Checkpoint — action required";
}
