import type { JobState, RunData, StageInfo } from "../types";
import { findHandoffStage, findPendingFocusStage } from "./checkpoint";
import { findNextRunnableStage, resolvePrecleanOffer } from "./preclean";

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

const PHASE_LABELS: Record<string, string> = {
  prepare: "Prepare",
  understand: "Analyze",
  complete: "Complete",
  create: "Build",
  polish: "Sound",
  ship: "Export",
  analysis: "Analyze",
  flow1: "Build",
  flow2: "Build",
  flow3: "Export",
  gate: "Checkpoint",
};

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
  const nextRunnable = findNextRunnableStage(run.stages);
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

  if (opts.jobRunning || job?.status === "running" || job?.status === "running_with_warnings") {
    statusLine = job?.message || `Running ${job?.stage || "pipeline"}…`;
    nextLine = "Watch Logs for progress.";
  } else if (job?.status === "gate" || run.stages.some((s) => s.status === "action_required")) {
    const gate =
      run.stages.find((s) => s.status === "action_required") ||
      run.stages.find((s) => s.id === job?.stage);
    statusLine = gate
      ? `${gate.title} needs your input`
      : job?.message || "Checkpoint — action required";
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
): "done" | "current" | "blocked" | "upcoming" {
  const { stage } = entry;
  if (stage.status === "done") return "done";
  if (stage.status === "action_required") return "blocked";
  if (stage.status === "locked") return "upcoming";
  if (
    stage.id === focusStageId ||
    stage.id === selectedStageId ||
    stage.id === run.job?.stage
  ) {
    return "current";
  }
  const next = findNextRunnableStage(run.stages);
  if (next?.id === stage.id) return "current";
  return "upcoming";
}

export function jobBlocksPipeline(job: JobState | undefined): boolean {
  if (!job?.status) return false;
  return ["running", "running_with_warnings"].includes(job.status);
}
