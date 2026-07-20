import type {
  GuidanceItem,
  PipelineSubTab,
  RunData,
  StageInfo,
  StageProgressSummary,
  StageSubstep,
  StageSubstepStatus,
  SubstepKind,
} from "../types";
import { listAttentionItems, type AttentionItem } from "./attentionQueue";
import { getHandoffPathsLocal } from "./checkpoint";
import { flattenGuidanceItems } from "./stageGuidance";
import { isOptionalStageSkipped, resolvePrecleanOffer } from "./preclean";
import { isWriteApprovalSaving } from "./jobStatus";
import { stageHasCommittedOutputs } from "./stageOutputs";

const USER_ACTION_KINDS = new Set<SubstepKind>([
  "blocked",
  "write_approval",
  "gate",
  "reuse",
  "optional",
  "handoff",
  "milestone",
  "checkpoint",
]);

function stageAwaitingWriteApproval(run: RunData | null, stageId: string): boolean {
  if (!run) return false;
  const stage = run.stages.find((s) => s.id === stageId);
  return (
    stage?.status === "awaiting_write_approval" ||
    Boolean(
      run.job?.awaiting_write_approval &&
        (run.job.pending_write_stage === stageId || run.job.stage === stageId),
    )
  );
}

export interface BuildSubstepsOpts {
  jobRunning?: boolean;
  actionBusy?: boolean;
  apiGrants?: Record<string, boolean>;
}

function guidanceStatusToSubstep(status: GuidanceItem["status"]): StageSubstepStatus {
  if (status === "todo") return "todo";
  if (status === "waiting") return "waiting";
  return "done";
}

function guidanceKindToSubstepKind(kind?: string, action?: string): SubstepKind {
  const k = kind || action || "guidance";
  switch (k) {
    case "write_approval":
      return "write_approval";
    case "checkpoint":
      return "checkpoint";
    case "gate":
      return "gate";
    case "handoff":
      return "handoff";
    case "reuse":
    case "stage_reuse":
      return "reuse";
    case "run":
      return "run";
    case "profile":
      return "profile";
    case "story_board":
      return "story_board";
    case "start":
      return "start";
    case "milestone":
      return "milestone";
    case "blocked":
      return "blocked";
    default:
      return "guidance";
  }
}

function targetForKind(
  kind: SubstepKind,
  subTab?: PipelineSubTab,
): { targetSection?: string; targetSubTab?: PipelineSubTab } {
  switch (kind) {
    case "write_approval":
      return { targetSection: "modal-write-approval", targetSubTab: "files" };
    case "gate":
    case "blocked":
    case "checkpoint":
      return { targetSection: "modal-gates", targetSubTab: subTab ?? "stage" };
    case "handoff":
      return { targetSection: "modal-handoff", targetSubTab: "files" };
    case "reuse":
      return { targetSection: "modal-reuse", targetSubTab: "stage" };
    case "profile":
      return { targetSubTab: "profile" };
    case "story_board":
    case "milestone":
      return { targetSubTab: "story" };
    default:
      return { targetSubTab: subTab ?? "stage" };
  }
}

export function guidanceItemToSubstep(item: GuidanceItem, stageId: string): StageSubstep {
  const kind = guidanceKindToSubstepKind(item.kind, item.action);
  const targets = targetForKind(kind);
  const displayLabel = item.substep_label || item.label;
  return {
    id: item.id,
    label: displayLabel,
    status: guidanceStatusToSubstep(item.status),
    kind,
    stageId: item.stage_id || stageId,
    source: "guidance",
    primaryLabel: item.substep_label ? item.label : undefined,
    ...targets,
  };
}

export function attentionItemToSubstep(item: AttentionItem): StageSubstep {
  const kindMap: Record<AttentionItem["kind"], SubstepKind> = {
    gate: "gate",
    write_approval: "write_approval",
    stage_reuse: "reuse",
    handoff: "handoff",
    blocked: "blocked",
    milestone: "milestone",
    optional: "optional",
    llm_verification_failed: "blocked",
  };
  const kind = kindMap[item.kind] ?? "guidance";
  const targets = targetForKind(kind, item.subTab);
  return {
    id: `${item.kind}:${item.stageId}`,
    label: item.title,
    status: "todo",
    kind,
    stageId: item.stageId,
    source: "attention",
    primaryLabel: item.primaryLabel,
    fileCount: item.fileCount,
    ...targets,
  };
}

function dedupeKey(sub: StageSubstep): string {
  return `${sub.kind}:${sub.id}`;
}

function mergeSubsteps(guidance: StageSubstep[], attention: StageSubstep[]): StageSubstep[] {
  const map = new Map<string, StageSubstep>();
  for (const g of guidance) {
    map.set(dedupeKey(g), g);
  }
  for (const a of attention) {
    const key = dedupeKey(a);
    const existing = map.get(key);
    if (existing) {
      map.set(key, {
        ...existing,
        ...a,
        label: a.label || existing.label,
        status: a.status === "todo" ? "todo" : existing.status,
        source: "attention",
        primaryLabel: a.primaryLabel ?? existing.primaryLabel,
        fileCount: a.fileCount ?? existing.fileCount,
      });
    } else if (a.kind === "write_approval") {
      const writeKey = [...map.entries()].find(([, v]) => v.kind === "write_approval")?.[0];
      if (writeKey) map.delete(writeKey);
      map.set(key, a);
    } else {
      map.set(key, a);
    }
  }
  return [...map.values()];
}

function isRunningStage(stage: StageInfo, run: RunData, jobRunning: boolean): boolean {
  if (!jobRunning || !run.job) return false;
  const sid = run.job.current_stage || run.job.stage;
  return sid === stage.id;
}

export function buildStageSubsteps(
  stage: StageInfo,
  run: RunData,
  opts: BuildSubstepsOpts = {},
): StageSubstep[] {
  const { jobRunning = false, actionBusy = false, apiGrants = {} } = opts;

  const guidanceSubs = flattenGuidanceItems(stage.guidance).map((item) =>
    guidanceItemToSubstep(item, stage.id),
  );

  const attentionSubs = listAttentionItems(run, apiGrants)
    .filter((item) => item.stageId === stage.id)
    .map(attentionItemToSubstep);

  let substeps = mergeSubsteps(guidanceSubs, attentionSubs);

  const running = isRunningStage(stage, run, jobRunning);
  if (running) {
    const runIdx = substeps.findIndex((s) => s.kind === "run");
    if (runIdx >= 0) {
      substeps = substeps.map((s, i) =>
        i === runIdx ? { ...s, status: "running" as const, label: `Running ${stage.title}…` } : s,
      );
    } else {
      substeps.push({
        id: "running",
        label: `Running ${stage.title}…`,
        status: "running",
        kind: "run",
        stageId: stage.id,
        source: "runtime",
        targetSubTab: "stage",
      });
    }
  }

  const jobFailed = run.job?.status === "error";
  const failedStageId = run.job?.current_stage || run.job?.stage;
  if (jobFailed && failedStageId === stage.id) {
    const errorMsg =
      run.job?.last_error?.message || run.job?.message || `Failed — ${stage.title}`;
    const runIdx = substeps.findIndex((s) => s.kind === "run");
    if (runIdx >= 0) {
      substeps = substeps.map((s, i) =>
        i === runIdx ? { ...s, status: "error" as const, label: errorMsg } : s,
      );
    } else {
      substeps.push({
        id: "error",
        label: errorMsg,
        status: "error",
        kind: "run",
        stageId: stage.id,
        source: "runtime",
        targetSubTab: "stage",
      });
    }
  }

  if (actionBusy && stageAwaitingWriteApproval(run, stage.id)) {
    substeps = substeps.map((s) =>
      s.kind === "write_approval"
        ? { ...s, status: "running", label: "Saving staged outputs — please wait…" }
        : s,
    );
  } else if (isWriteApprovalSaving(run.job) && stageAwaitingWriteApproval(run, stage.id)) {
    substeps = substeps.map((s) =>
      s.kind === "write_approval"
        ? { ...s, status: "running", label: "Saving staged outputs — please wait…" }
        : s,
    );
  } else if (
    actionBusy &&
    stage.id === "analysis_profile" &&
    stage.status === "action_required"
  ) {
    substeps = substeps.map((s) =>
      s.kind === "gate" || s.kind === "profile" || s.id.includes("profile")
        ? { ...s, status: "running", label: "Verifying profile…" }
        : s,
    );
  } else if (
    actionBusy &&
    hasUnackedHandoff(stage, run)
  ) {
    substeps = substeps.map((s) =>
      s.kind === "handoff"
        ? { ...s, status: "running", label: "Acknowledging handoff…" }
        : s,
    );
  } else if (!stageAwaitingWriteApproval(run, stage.id)) {
    substeps = substeps.map((s) =>
      s.kind === "write_approval" && s.status !== "done"
        ? { ...s, status: "done", label: "Saved to disk" }
        : s,
    );
  }

  const offer = resolvePrecleanOffer(stage, run.meta);
  if (offer && stage.id === "g1_vo_pickup" && !isOptionalStageSkipped(stage, run.meta)) {
    const hasOptional = substeps.some((s) => s.kind === "optional");
    if (!hasOptional) {
      substeps.push(
        {
          id: "optional:review",
          label: "Review optional pickup cleaning",
          status: "todo",
          kind: "optional",
          stageId: stage.id,
          source: "attention",
          primaryLabel: "Run pickup cleaning",
          targetSubTab: "stage",
        },
      );
    }
  } else if (
    offer &&
    stage.id === "audio_preclean" &&
    !isOptionalStageSkipped(stage, run.meta)
  ) {
    substeps.push({
      id: "preclean:run",
      label: "Run audio cleaning",
      status: stage.status === "done" ? "done" : "todo",
      kind: "checkpoint",
      stageId: stage.id,
      source: "attention",
      primaryLabel: "Run audio cleaning",
      targetSubTab: "stage",
    });
  }

  const hintId = run.journey?.active_substep_id;
  if (hintId) {
    substeps = substeps.map((s) => {
      if (s.status !== "todo") return s;
      const matches =
        s.id === hintId ||
        (hintId.startsWith("blocked:") && s.id === hintId) ||
        ((hintId === "write_approval" || hintId.startsWith("write_approval:")) &&
          s.kind === "write_approval") ||
        ((hintId === "stage_reuse" || hintId.startsWith("stage_reuse:")) &&
          s.kind === "reuse") ||
        ((hintId === "handoff" || hintId.startsWith("handoff:")) &&
          s.kind === "handoff") ||
        (hintId.startsWith("gate:") && s.kind === "gate") ||
        (hintId.startsWith("blocked:") && s.kind === "blocked");
      if (!matches || USER_ACTION_KINDS.has(s.kind)) return s;
      return { ...s, status: "running" as const };
    });
  }

  return substeps;
}

function hasUnackedHandoff(stage: StageInfo, run: RunData): boolean {
  if (stage.status !== "done") return false;
  const paths = getHandoffPathsLocal(stage, run.log_tail);
  return paths.length > 0 && !run.handoff_ack?.[stage.id];
}

export function buildStageProgress(
  stage: StageInfo,
  run: RunData,
  opts: BuildSubstepsOpts = {},
): StageProgressSummary {
  const substeps = buildStageSubsteps(stage, run, opts);
  const hasTodo = substeps.some((s) => s.status === "todo");
  const hasRunning = substeps.some((s) => s.status === "running");
  const hasError = substeps.some((s) => s.status === "error");
  const activeSubstep =
    substeps.find((s) => s.status === "error") ??
    substeps.find((s) => s.status === "running") ??
    substeps.find((s) => s.status === "todo") ??
    null;
  const doneCount = substeps.filter((s) => s.status === "done").length;
  const totalCount = substeps.length;
  const optionalSkipped = isOptionalStageSkipped(stage, run.meta);
  const fullyComplete =
    optionalSkipped ||
    (stage.status === "done" &&
      stageHasCommittedOutputs(stage) &&
      !hasTodo &&
      !hasRunning &&
      !hasError &&
      !hasUnackedHandoff(stage, run) &&
      !stageAwaitingWriteApproval(run, stage.id));

  if (optionalSkipped) {
    const settledSubsteps = substeps.map((s) =>
      s.status === "done" ? s : { ...s, status: "done" as const },
    );
    return {
      stageId: stage.id,
      substeps: settledSubsteps,
      fullyComplete: true,
      hasTodo: false,
      hasRunning: false,
      hasError: false,
      activeSubstep: null,
      doneCount: settledSubsteps.length,
      totalCount: settledSubsteps.length,
    };
  }

  return {
    stageId: stage.id,
    substeps,
    fullyComplete,
    hasTodo,
    hasRunning,
    hasError,
    activeSubstep,
    doneCount,
    totalCount,
  };
}

export function buildAllStageProgress(
  run: RunData,
  opts: BuildSubstepsOpts = {},
): Map<string, StageProgressSummary> {
  const map = new Map<string, StageProgressSummary>();
  for (const stage of run.stages) {
    map.set(stage.id, buildStageProgress(stage, run, opts));
  }
  return map;
}

export function findActiveSubstep(
  run: RunData,
  opts: BuildSubstepsOpts = {},
): StageSubstep | null {
  for (const stage of run.stages) {
    const progress = buildStageProgress(stage, run, opts);
    const errored = progress.substeps.find((s) => s.status === "error");
    if (errored) return errored;
    const running = progress.substeps.find((s) => s.status === "running" && s.kind === "run");
    if (running) return running;
    const saving = progress.substeps.find(
      (s) => s.status === "running" && s.kind === "write_approval",
    );
    if (saving) return saving;
  }
  const hintId = run.journey?.active_substep_id;
  if (hintId) {
    for (const stage of run.stages) {
      const progress = buildStageProgress(stage, run, opts);
      const match = progress.substeps.find(
        (s) =>
          s.id === hintId ||
          (hintId.startsWith("blocked:") && s.id === hintId) ||
          ((hintId === "write_approval" || hintId.startsWith("write_approval:")) &&
          s.kind === "write_approval") ||
        ((hintId === "stage_reuse" || hintId.startsWith("stage_reuse:")) &&
          s.kind === "reuse") ||
        ((hintId === "handoff" || hintId.startsWith("handoff:")) &&
          s.kind === "handoff") ||
          (hintId.startsWith("gate:") && s.kind === "gate") ||
          (hintId.startsWith("blocked:") && s.kind === "blocked"),
      );
      if (match) return match;
    }
  }
  for (const stage of run.stages) {
    const progress = buildStageProgress(stage, run, opts);
    if (progress.activeSubstep) return progress.activeSubstep;
  }
  return null;
}

export function shouldShowRunningConnector(
  prevStage: StageInfo | null,
  nextStage: StageInfo | null,
  run: RunData,
  jobRunning: boolean,
  actionBusy = false,
): boolean {
  if (!jobRunning && !actionBusy) return false;
  if (!run.job) return false;
  const jobStageId = run.job.current_stage || run.job.stage;
  if (!jobStageId) return false;
  if (prevStage?.id === jobStageId || nextStage?.id === jobStageId) return true;
  if (actionBusy && prevStage && stageAwaitingWriteApproval(run, prevStage.id)) return true;
  return false;
}

/** Todo/running substep counts per pipeline sub-tab (for tool row badges). */
export function subTabSubstepFlags(
  run: RunData,
  opts: BuildSubstepsOpts = {},
): Partial<Record<PipelineSubTab, { count: number; labels: string[] }>> {
  const flags: Partial<Record<PipelineSubTab, { count: number; labels: string[] }>> = {};
  for (const stage of run.stages) {
    const progress = buildStageProgress(stage, run, opts);
    for (const sub of progress.substeps) {
      if (sub.status !== "todo" && sub.status !== "running" && sub.status !== "error") continue;
      const tab = sub.targetSubTab ?? "stage";
      const entry = flags[tab] ?? { count: 0, labels: [] };
      entry.count += 1;
      if (entry.labels.length < 3) entry.labels.push(sub.label);
      flags[tab] = entry;
    }
  }
  return flags;
}

export function pendingActionToSubstep(
  pending: {
    kind: AttentionItem["kind"];
    stageId: string;
    title: string;
    primaryLabel: string;
    fileCount?: number;
    subTab?: PipelineSubTab;
  },
): StageSubstep {
  return attentionItemToSubstep({
    kind: pending.kind,
    priority: 1,
    stageId: pending.stageId,
    stageTitle: "",
    title: pending.title,
    message: "",
    primaryLabel: pending.primaryLabel,
    fileCount: pending.fileCount,
    subTab: pending.subTab,
    phase: "prepare",
  });
}
