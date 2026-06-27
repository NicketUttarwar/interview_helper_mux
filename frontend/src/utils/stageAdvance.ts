import type { RunData, StageInfo } from "../types";
import { focusStageWorkbench, type FocusStageWorkbenchOpts } from "./checkpointContinuation";
import { findNextRunnableStage } from "./preclean";
import {
  tryAcceptStageReuseFromAssets,
  type StageReuseFromAssetsResult,
} from "./stageReuseFromAssets";

export function readyForStageMessage(title: string): string {
  return `Ready for ${title} — use Run when you want to start.`;
}

export type StageWorkbenchDeps = Pick<
  FocusStageWorkbenchOpts,
  "selectStage" | "expandStage" | "setActiveStepId" | "setPipelineSubTab"
>;

export async function focusNextRunnableStageWorkbench(
  run: RunData,
  deps: StageWorkbenchDeps,
): Promise<StageInfo | null> {
  const next = findNextRunnableStage(run.stages, run.meta);
  if (!next) return null;
  await focusStageWorkbench({
    run,
    ...deps,
    stageId: next.id,
    substepId: "run",
  });
  return next;
}

export interface ApplyReuseResultOpts extends StageWorkbenchDeps {
  run: RunData;
  stageId: string;
  stageTitle: string;
  reuse: Extract<StageReuseFromAssetsResult, { status: "reused" }>;
  refreshRun: () => Promise<RunData | null>;
  showToast: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  announceNext?: boolean;
  /** When autopilot is on, chain into the next stage after reuse lands. */
  autoContinuePipeline?: (completedStageId?: string | null) => Promise<boolean>;
}

/** After reuse copies land, focus write approval or continue the pipeline. */
export async function applyReuseResultAndFocus(opts: ApplyReuseResultOpts): Promise<void> {
  const refreshed = (await opts.refreshRun()) ?? opts.run;
  if (opts.reuse.hasStagedWrites) {
    opts.showToast(
      `Reused prior ${opts.stageTitle} outputs — review staged files before saving.`,
      "success",
    );
    await focusStageWorkbench({
      run: refreshed,
      stageId: opts.stageId,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      substepId: "write_approval",
      blockingReason: "write_approval",
    });
    return;
  }

  opts.showToast(`Reused prior ${opts.stageTitle} outputs from ASSETS.`, "success");
  const nextRefreshed = (await opts.refreshRun()) ?? refreshed;
  if (opts.autoContinuePipeline) {
    const continued = await opts.autoContinuePipeline(opts.stageId);
    if (continued) return;
  }
  const next = await focusNextRunnableStageWorkbench(nextRefreshed, opts);
  if (next && opts.announceNext !== false) {
    opts.showToast(readyForStageMessage(next.title), "info");
  }
}

export interface TryReuseFromAssetsOpts extends StageWorkbenchDeps {
  runId: string;
  run: RunData;
  stage: StageInfo;
  refreshRun: () => Promise<RunData | null>;
  showToast: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  autoContinuePipeline?: (completedStageId?: string | null) => Promise<boolean>;
}

/** Try copying validated prior-run outputs from ASSETS for this stage. */
export async function tryReuseFromAssetsForStage(
  opts: TryReuseFromAssetsOpts,
): Promise<StageReuseFromAssetsResult> {
  return tryAcceptStageReuseFromAssets(opts.runId, opts.stage.id);
}

export async function handleReuseFromAssetsForStage(
  opts: TryReuseFromAssetsOpts,
): Promise<"reused" | "no_candidates" | "failed"> {
  const reuse = await tryReuseFromAssetsForStage(opts);
  if (reuse.status === "reused") {
    await applyReuseResultAndFocus({
      run: opts.run,
      stageId: opts.stage.id,
      stageTitle: opts.stage.title,
      reuse,
      refreshRun: opts.refreshRun,
      showToast: opts.showToast,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      autoContinuePipeline: opts.autoContinuePipeline,
    });
    return "reused";
  }
  if (reuse.status === "failed") {
    opts.showToast(reuse.message, "error");
    return "failed";
  }
  return "no_candidates";
}
