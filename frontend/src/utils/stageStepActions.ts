import type { ExecuteBody, StageInfo, StageStep } from "../types";
import type { OperatorAction } from "../types/operatorAction";
import { executeBodyForStage } from "./operatorActionHandlers";
import { runStepPrimaryPreps } from "./stepPrimaryPrep";

interface StepActionHandlers {
  executeJob: (body: ExecuteBody) => Promise<void>;
  runNextStage: () => Promise<void>;
  advanceFromCheckpoint: () => Promise<void>;
  completeTranscriptReview: (acceptUnreviewed?: boolean) => Promise<void>;
  approveSfxPrompts: () => Promise<void>;
  skipOptional: (stageId: string) => Promise<void>;
  declineReuseAndRun: (stageId: string) => Promise<void>;
  redoFromStage: () => Promise<void>;
  selectStage: (stageId: string) => Promise<void>;
  stageAction: OperatorAction | null;
}

export async function invokeStepFooterAction(
  step: StageStep,
  stage: StageInfo,
  handlers: StepActionHandlers,
): Promise<void> {
  const label = (step.primary_button || "").toLowerCase();

  if (step.kind === "run" || label.startsWith("run ")) {
    await handlers.executeJob(executeBodyForStage(stage.id));
    return;
  }

  if (step.kind === "locked" && step.blocking_reason) {
    await handlers.selectStage(step.blocking_reason);
    return;
  }

  if (
    step.id === "review_transcript" ||
    step.id === "complete_g0" ||
    (step.embed === "transcript_review" &&
      (label.includes("complete transcript") || label.includes("save and complete")))
  ) {
    await runStepPrimaryPreps(["transcript_dock_flush", "transcript_review_flush", step.id]);
    await handlers.completeTranscriptReview(false);
    return;
  }

  if (
    step.id === "prompt_review" ||
    (step.embed === "sfx_prompt_review" && label.includes("approve"))
  ) {
    await runStepPrimaryPreps(["sfx_prompt_review", step.id]);
    await handlers.approveSfxPrompts();
    return;
  }

  if (
    label.includes("continue") ||
    step.kind === "done" ||
    label.includes("continue to")
  ) {
    await handlers.advanceFromCheckpoint();
    return;
  }

  if (step.kind === "reuse" && label.includes("reuse")) {
    return;
  }

  if (step.kind === "preclean" && label.includes("skip")) {
    await handlers.skipOptional(stage.id);
    return;
  }

  if (step.kind === "preclean" && label.includes("clean")) {
    await handlers.executeJob({ mode: "stage", stage: stage.id });
    return;
  }

  if (handlers.stageAction?.primaryKind === "continue_next") {
    await handlers.runNextStage();
    return;
  }

  if (handlers.stageAction?.primaryKind === "run_stage") {
    await handlers.executeJob(executeBodyForStage(stage.id));
    return;
  }

  await handlers.advanceFromCheckpoint();
}

export async function invokeStepFooterSecondaryAction(
  step: StageStep,
  stage: StageInfo,
  handlers: Pick<
    StepActionHandlers,
    "completeTranscriptReview" | "skipOptional" | "declineReuseAndRun" | "redoFromStage"
  >,
): Promise<void> {
  const label = (step.secondary_button || "").toLowerCase();

  if (label.includes("accept remaining")) {
    await handlers.completeTranscriptReview(true);
    return;
  }

  if (label.includes("redo")) {
    await handlers.redoFromStage();
    return;
  }

  if (step.kind === "preclean" && label.includes("skip")) {
    await handlers.skipOptional(stage.id);
    return;
  }

  if (step.kind === "reuse" && label.includes("fresh")) {
    await handlers.declineReuseAndRun(stage.id);
  }
}
