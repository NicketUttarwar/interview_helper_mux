import type { RunData, StageInfo } from "../types";
import { PHASE_LABELS } from "../constants/phases";
import { findHandoffStage, findPendingFocusStage } from "./checkpoint";
import {
  gateStatusLine,
  resolveJobStatusContext,
  reuseStatusLine,
  writeApprovalStatusLine,
} from "./operatorStatus";
import { findNextRunnableStage, isOptionalStageSkipped, resolvePrecleanOffer } from "./preclean";
import { stageArtifactsFullyComplete, stageHasCommittedOutputs } from "./stageOutputs";

export interface NumberedStage {
  number: number;
  stage: StageInfo;
  phaseLabel: string;
}

export interface PipelineNavState {
  numberedStages: NumberedStage[];
  currentStage: StageInfo | null;
  currentNumber: number | null;
  nextStage: StageInfo | null;
  nextNumber: number | null;
  focusStageId: string | null;
  handoffStage: StageInfo | null;
  statusLine: string;
  nextLine: string;
  primaryAction: "run_next" | "checkpoint" | "handoff" | "none";
  canRunNext: boolean;
  precleanOffer: ReturnType<typeof resolvePrecleanOffer>;
}

function visibleStages(stages: StageInfo[]): StageInfo[] {
  return stages;
}

export function buildNumberedStages(stages: StageInfo[]): NumberedStage[] {
  const visible = visibleStages(stages);
  return visible.map((stage, i) => ({
    number: i + 1,
    stage,
    phaseLabel: PHASE_LABELS[stage.operator_phase ?? stage.phase ?? ""] ?? "Step",
  }));
}

function findNumbered(
  numbered: NumberedStage[],
  stageId: string | null | undefined,
): NumberedStage | undefined {
  if (!stageId) return undefined;
  return numbered.find((n) => n.stage.id === stageId);
}

export function resolvePipelineNav(
  run: RunData | null,
  opts: {
    selectedStageId: string | null;
    jobRunning: boolean;
    apiGrants: Record<string, boolean>;
  },
): PipelineNavState {
  const empty: PipelineNavState = {
    numberedStages: [],
    currentStage: null,
    currentNumber: null,
    nextStage: null,
    nextNumber: null,
    focusStageId: null,
    handoffStage: null,
    statusLine: "Open a run to see pipeline steps.",
    nextLine: "",
    primaryAction: "none",
    canRunNext: false,
    precleanOffer: null,
  };

  if (!run) return empty;

  const numbered = buildNumberedStages(run.stages);
  const handoffStage = findHandoffStage(run);
  const focusStageId = findPendingFocusStage(run, opts.apiGrants);
  const nextRunnable = findNextRunnableStage(run.stages, run.meta);
  const job = run.job;

  let currentStage: StageInfo | null = null;
  if (focusStageId) {
    currentStage = run.stages.find((s) => s.id === focusStageId) ?? null;
  } else if (handoffStage) {
    currentStage = handoffStage;
  } else if (opts.selectedStageId) {
    currentStage = run.stages.find((s) => s.id === opts.selectedStageId) ?? null;
  } else if (nextRunnable) {
    currentStage = nextRunnable;
  }

  const currentNumber = findNumbered(numbered, currentStage?.id)?.number ?? null;
  const nextStageResolved = nextRunnable ?? null;
  const nextNumber = findNumbered(numbered, nextStageResolved?.id)?.number ?? null;

  const precleanStage = run.stages.find((s) => s.id === "audio_preclean");
  const precleanTarget =
    currentStage?.id === "audio_preclean"
      ? currentStage
      : nextRunnable?.id === "audio_preclean"
        ? precleanStage
        : null;
  const precleanOffer = precleanTarget
    ? resolvePrecleanOffer(precleanTarget, run.meta)
    : null;

  let statusLine = run.journey?.next_action || "Select a step or run the next stage.";
  let nextLine = "";
  let primaryAction: PipelineNavState["primaryAction"] = "none";
  let canRunNext = false;

  const jobCtx = resolveJobStatusContext(run, opts.jobRunning);

  if (jobCtx.isRunning) {
    statusLine = job?.message || `Running ${job?.stage || "pipeline"}…`;
    nextLine = "Watch Logs for progress.";
  } else if (jobCtx.awaitingWriteApproval) {
    statusLine = writeApprovalStatusLine(run, job);
    nextLine = "Approve or discard staged files in the checkpoint panel.";
    primaryAction = "checkpoint";
    canRunNext = true;
  } else if (jobCtx.needsStageReuse || jobCtx.needsStageReuseFromJourney) {
    const reuseStageId = job?.stage || jobCtx.journeyReuseStageId;
    const reuseJob = reuseStageId ? { ...job, stage: reuseStageId } : job;
    statusLine = reuseStatusLine(run, reuseJob);
    nextLine = "Pick a prior run with the same source audio hash, or run this step fresh.";
    primaryAction = "checkpoint";
    canRunNext = true;
  } else if (jobCtx.needsGate) {
    const gate =
      jobCtx.actionRequiredStage ||
      run.stages.find((s) => s.id === job?.stage);
    statusLine = gateStatusLine(run, job, jobCtx.actionRequiredStage);
    nextLine = gate ? `Complete ${gate.title}, then continue.` : "Open the checkpoint panel.";
    primaryAction = "checkpoint";
    canRunNext = true;
  } else if (handoffStage) {
    statusLine = `${handoffStage.title} finished — review AI outputs`;
    nextLine = nextStageResolved
      ? `Next: Step ${nextNumber ?? "?"} — ${nextStageResolved.title}`
      : "Acknowledge review to continue.";
    primaryAction = "handoff";
    canRunNext = true;
  } else if (nextRunnable) {
    statusLine = `Up next: Step ${nextNumber ?? "?"} — ${nextRunnable.title}`;
    nextLine = "Run the next step when you are ready.";
    primaryAction = "run_next";
    canRunNext = true;
  } else {
    statusLine = "Pipeline idle — all visible steps complete or locked.";
    nextLine = run.journey?.deliverable?.kind
      ? "Your deliverable may be ready in Export."
      : "Check locked stages or choose a flow at G2.";
  }

  return {
    numberedStages: numbered,
    currentStage,
    currentNumber,
    nextStage: nextStageResolved,
    nextNumber,
    focusStageId,
    handoffStage,
    statusLine,
    nextLine,
    primaryAction,
    canRunNext,
    precleanOffer,
  };
}

export function stageNavStatus(
  entry: NumberedStage,
  run: RunData,
  selectedStageId: string | null,
  focusStageId: string | null,
): "done" | "current" | "blocked" | "upcoming" | "skipped" {
  const { stage } = entry;
  if (isOptionalStageSkipped(stage, run.meta)) return "skipped";
  if (stage.status === "incomplete") return "blocked";
  if (stage.status === "done" && !stageArtifactsFullyComplete(stage)) return "blocked";
  if (stage.status === "done") return "done";
  if (stage.status === "action_required" || stage.status === "awaiting_write_approval") {
    return "blocked";
  }
  if (stage.status === "locked") return "upcoming";
  if (
    stage.id === focusStageId ||
    stage.id === selectedStageId ||
    stage.id === run.job?.stage
  ) {
    return "current";
  }
  const next = findNextRunnableStage(run.stages, run.meta);
  if (next?.id === stage.id) return "current";
  return "upcoming";
}
