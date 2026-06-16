import type { OperatorPhase, PipelineSubTab, RunData, StageInfo } from "../types";
import {
  findPendingFocusStage,
  getHandoffPathsLocal,
} from "./checkpoint";
import { checkpointPrimaryLabel } from "./checkpointLabels";
import { resolveJobStatusContext } from "./operatorStatus";
import { parseFileCountFromMessage } from "./pendingAction";
import { resolvePrecleanOffer } from "./preclean";
export type WorkflowStepStatus = "done" | "active" | "upcoming" | "attention";
export type WorkflowStepId =
  | "start"
  | "prepare"
  | "understand"
  | "complete"
  | "create"
  | "polish"
  | "ship";

export type AttentionKind =
  | "gate"
  | "write_approval"
  | "stage_reuse"
  | "handoff"
  | "blocked"
  | "milestone"
  | "optional";

export interface AttentionItem {
  kind: AttentionKind;
  priority: number;
  stageId: string;
  stageTitle: string;
  title: string;
  message: string;
  primaryLabel: string;
  phase: OperatorPhase;
  subTab?: PipelineSubTab;
  fileCount?: number;
  optional?: boolean;
  handoffPaths?: string[];
}

const PHASE_ORDER: OperatorPhase[] = [
  "prepare",
  "understand",
  "complete",
  "create",
  "polish",
  "ship",
];

function stagePhase(stage: StageInfo): OperatorPhase {
  const op = stage.operator_phase ?? stage.phase ?? "understand";
  if (op === "gate") return "complete";
  return op as OperatorPhase;
}

function subTabForStage(stageId: string, kind: AttentionKind): PipelineSubTab {
  if (kind === "handoff" || kind === "write_approval") return "files";
  if (stageId === "analysis_profile") return "story";
  if (stageId.startsWith("nle") || stageId.includes("edl")) return "timeline";
  return "stage";
}

function parseCountFromMessage(msg: string | undefined, re: RegExp): number | undefined {
  if (!msg) return undefined;
  const m = msg.match(re);
  return m ? parseInt(m[1], 10) : undefined;
}

function gateItem(
  run: RunData,
  stage: StageInfo,
  message?: string,
): AttentionItem {
  const clipCount = parseCountFromMessage(message, /Review (\d+) ranked STT/);
  const pickupCount =
    parseCountFromMessage(message, /Record (\d+) pickup/) ??
    (stage.id === "g1_vo_pickup" ? run.g1_missing?.length : undefined);
  return {
    kind: "gate",
    priority: 1,
    stageId: stage.id,
    stageTitle: stage.title,
    title: `${stage.title} needs your input`,
    message: message || "Complete the required steps in the checkpoint panel to continue.",
    primaryLabel: checkpointPrimaryLabel(stage.id, "gate", { clipCount, pickupCount }),
    phase: stagePhase(stage),
    subTab: subTabForStage(stage.id, "gate"),
  };
}

function writeApprovalItem(run: RunData, stageId: string, message?: string): AttentionItem {
  const stage = run.stages.find((s) => s.id === stageId);
  const fileCount = parseFileCountFromMessage(message);
  return {
    kind: "write_approval",
    priority: 2,
    stageId,
    stageTitle: stage?.title || stageId.replace(/_/g, " "),
    title: fileCount
      ? `Review ${fileCount} file${fileCount === 1 ? "" : "s"} before saving`
      : "Review outputs before saving",
    message:
      message ||
      `${stage?.title || "This step"} produced outputs that need your approval before writing to disk.`,
    primaryLabel: checkpointPrimaryLabel(stageId, "write_approval", { fileCount }),
    phase: stage ? stagePhase(stage) : (run.journey?.phase ?? "prepare"),
    subTab: "files",
    fileCount,
  };
}

function handoffItem(run: RunData, stage: StageInfo): AttentionItem {
  const paths = getHandoffPathsLocal(stage, run.log_tail);
  const pathHint =
    paths.length > 0
      ? `Check: ${paths
          .slice(0, 2)
          .map((p) => p.split("/").pop())
          .join(", ")}${paths.length > 2 ? "…" : ""}`
      : "Check the generated content above, then acknowledge to continue.";
  return {
    kind: "handoff",
    priority: 4,
    stageId: stage.id,
    stageTitle: stage.title,
    title: `${stage.title} finished — review AI outputs`,
    message: pathHint,
    primaryLabel: checkpointPrimaryLabel(stage.id, "handoff"),
    phase: stagePhase(stage),
    subTab: "files",
    handoffPaths: paths,
  };
}

/** All operator attention items, highest priority first. */
export function listAttentionItems(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): AttentionItem[] {
  if (!run) return [];

  const items: AttentionItem[] = [];
  const job = run.job;
  const ctx = resolveJobStatusContext(run, false);
  const focusStageId = findPendingFocusStage(run, grants);
  const seen = new Set<string>();

  const push = (item: AttentionItem) => {
    const key = `${item.kind}:${item.stageId}`;
    if (seen.has(key)) return;
    seen.add(key);
    items.push(item);
  };

  for (const stage of run.stages) {
    if (stage.status === "action_required") {
      push(gateItem(run, stage));
    }
  }

  if (job?.status === "gate" && job.stage) {
    const stage = run.stages.find((s) => s.id === job.stage);
    if (stage) push(gateItem(run, stage, job.message));
    else {
      push({
        kind: "gate",
        priority: 1,
        stageId: job.stage,
        stageTitle: job.stage.replace(/_/g, " "),
        title: "Checkpoint required",
        message: job.message || "Action required before the pipeline can continue.",
        primaryLabel: checkpointPrimaryLabel(job.stage, "gate"),
        phase: run.journey?.phase ?? "prepare",
        subTab: "stage",
      });
    }
  }

  if (ctx.awaitingWriteApproval) {
    const sid = job?.pending_write_stage || job?.stage || focusStageId || "";
    if (sid) push(writeApprovalItem(run, sid, job?.message));
  }

  if (ctx.needsStageReuse && job?.stage) {
    const stage = run.stages.find((s) => s.id === job.stage);
    push({
      kind: "stage_reuse",
      priority: 3,
      stageId: job.stage,
      stageTitle: stage?.title || job.stage,
      title: stage ? `${stage.title} — reuse prior outputs?` : "Reuse from prior run?",
      message:
        job.message ||
        "Pick a previous execution with the same source audio hash and complete outputs, or run this step fresh.",
      primaryLabel: checkpointPrimaryLabel(job.stage, "stage_reuse"),
      phase: stage ? stagePhase(stage) : (run.journey?.phase ?? "prepare"),
      subTab: "stage",
    });
  }

  for (const stage of run.stages) {
    if (stage.status !== "done") continue;
    const paths = getHandoffPathsLocal(stage, run.log_tail);
    if (paths.length && !run.handoff_ack?.[stage.id]) {
      push(handoffItem(run, stage));
    }
  }

  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.stage_id) {
    const stage = run.stages.find((s) => s.id === blocking.stage_id);
    push({
      kind: "blocked",
      priority: 5,
      stageId: blocking.stage_id,
      stageTitle: stage?.title || blocking.stage_id,
      title: "Pipeline blocked",
      message: blocking.message || "Complete the required step to continue.",
      primaryLabel: checkpointPrimaryLabel(
        blocking.stage_id,
        "blocked",
        {
          clipCount: parseCountFromMessage(blocking.message, /Review (\d+) ranked STT/),
          pickupCount: parseCountFromMessage(blocking.message, /Record (\d+) pickup/),
        },
      ),
      phase: stage ? stagePhase(stage) : (run.journey?.phase ?? "prepare"),
      subTab: stage ? subTabForStage(stage.id, "blocked") : "stage",
    });
  }

  const milestones = run.journey?.milestones ?? run.meta?.journey_milestones ?? {};
  const previewPath = run.journey?.deliverable?.paths?.preview;
  if (
    milestones.preview_ready &&
    !milestones.preview_listened &&
    previewPath
  ) {
    push({
      kind: "milestone",
      priority: 6,
      stageId: "assembly_preview",
      stageTitle: "Assembly preview",
      title: "Listen to preview before sound spend",
      message: "Play the speech + VO preview, then continue to sound design.",
      primaryLabel: checkpointPrimaryLabel("assembly_preview", "milestone"),
      phase: "polish",
      subTab: "stage",
    });
  }

  if (run.profile_gate_pending && !run.profile_verified) {
    push({
      kind: "milestone",
      priority: 6,
      stageId: "analysis_profile",
      stageTitle: "Interview profile",
      title: "Review AI story profile",
      message: "Verify themes and tone on Story Board before extended Flow 1 stages.",
      primaryLabel: checkpointPrimaryLabel("analysis_profile", "milestone"),
      phase: "understand",
      subTab: "story",
    });
  }

  const inv = run.journey?.open_investigations ?? 0;
  if (inv > 0) {
    push({
      kind: "milestone",
      priority: 6,
      stageId: "investigation_queue",
      stageTitle: "Story Board",
      title: `Resolve ${inv} open question${inv === 1 ? "" : "s"}`,
      message: "Close investigations on Story Board before continuing analysis.",
      primaryLabel: "Open Story Board",
      phase: "understand",
      subTab: "story",
    });
  }

  const blockingCoherence = run.journey?.blocking_coherence_contradictions ?? 0;
  if (blockingCoherence > 0) {
    push({
      kind: "blocked",
      priority: 2,
      stageId: "analysis_profile",
      stageTitle: "Story Board",
      title: "Resolve blocking claim contradictions",
      message: `${blockingCoherence} blocking coherence contradiction(s) — re-anchor brief or resolve on Story Board.`,
      primaryLabel: "Open Story Board",
      phase: "understand",
      subTab: "story",
    });
  }

  for (const stage of run.stages) {
    const offer = resolvePrecleanOffer(stage, run.meta);
    if (offer) {
      push({
        kind: "optional",
        priority: 7,
        stageId: stage.id,
        stageTitle: stage.title,
        title: "Optional audio pre-clean",
        message: offer.prompt,
        primaryLabel: checkpointPrimaryLabel(stage.id, "optional"),
        phase: stagePhase(stage),
        subTab: "stage",
        optional: true,
      });
    }
  }

  return items.sort((a, b) => a.priority - b.priority);
}

export function listRequiredAttentionItems(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): AttentionItem[] {
  return listAttentionItems(run, grants).filter((i) => !i.optional);
}

export function topAttentionItem(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): AttentionItem | null {
  const required = listRequiredAttentionItems(run, grants);
  return required[0] ?? null;
}

export function countRequiredAttention(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): number {
  return listRequiredAttentionItems(run, grants).length;
}

export function stageNeedsAttention(
  run: RunData | null,
  stageId: string,
  grants: Record<string, boolean> = {},
): boolean {
  return listRequiredAttentionItems(run, grants).some((i) => i.stageId === stageId);
}

export function phaseHasAttention(
  run: RunData | null,
  phaseId: OperatorPhase,
  grants: Record<string, boolean> = {},
): boolean {
  return listRequiredAttentionItems(run, grants).some((i) => i.phase === phaseId);
}

export function attentionCountForPhase(
  run: RunData | null,
  phaseId: OperatorPhase,
  grants: Record<string, boolean> = {},
): number {
  return listRequiredAttentionItems(run, grants).filter((i) => i.phase === phaseId).length;
}

export function phaseAttentionStatus(
  stepId: WorkflowStepId,
  run: RunData | null,
  grants: Record<string, boolean> = {},
): WorkflowStepStatus {
  if (stepId === "start") {
    return run ? "done" : "active";
  }
  if (!run) return "upcoming";

  if (phaseHasAttention(run, stepId as OperatorPhase, grants)) {
    return "attention";
  }

  const phase = (run.journey?.phase ?? run.meta?.operator_phase ?? "prepare") as OperatorPhase;

  const stepIdx = PHASE_ORDER.indexOf(stepId as OperatorPhase);
  const currentIdx = PHASE_ORDER.indexOf(phase);
  if (stepIdx < 0 || currentIdx < 0) return "upcoming";

  if (stepIdx < currentIdx) return "done";
  if (stepIdx > currentIdx) return "upcoming";

  const prog = run.journey?.phase_progress?.[stepId];
  if (prog && prog.total > 0 && prog.done >= prog.total) return "done";
  return "active";
}

export function subTabAttentionFlags(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): Partial<Record<PipelineSubTab, number>> {
  if (!run) return {};
  const flags: Partial<Record<PipelineSubTab, number>> = {};

  const bump = (tab: PipelineSubTab, n = 1) => {
    flags[tab] = (flags[tab] ?? 0) + n;
  };

  for (const item of listRequiredAttentionItems(run, grants)) {
    if (item.subTab) bump(item.subTab);
    else bump("stage");
  }

  if ((run.journey?.open_investigations ?? 0) > 0) bump("story");
  if (run.profile_gate_pending && !run.profile_verified) bump("story");

  if (run.nle_dirty) bump("timeline");

  return flags;
}

export function phaseHasBlockingAttention(
  run: RunData,
  stepId: WorkflowStepId,
  grants: Record<string, boolean> = {},
): boolean {
  if (stepId === "start") return false;
  return listRequiredAttentionItems(run, grants).some(
    (i) => i.phase === stepId,
  );
}
