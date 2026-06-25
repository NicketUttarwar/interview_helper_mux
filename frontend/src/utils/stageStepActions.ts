import type { ExecuteBody, StageInfo, StageStep } from "../types";
import type { OperatorAction } from "../types/operatorAction";
import { executeBodyForStage } from "./operatorActionHandlers";

interface StepActionHandlers {
  executeJob: (body: ExecuteBody) => Promise<void>;
  runNextStage: () => Promise<void>;
  advanceFromCheckpoint: () => Promise<void>;
  skipOptional: (stageId: string) => Promise<void>;
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
    label.includes("continue") ||
    step.kind === "done" ||
    label.includes("continue to")
  ) {
    await handlers.advanceFromCheckpoint();
    return;
  }

  if (step.kind === "reuse" && label.includes("reuse")) {
    // Reuse cards handle accept — scroll only
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
