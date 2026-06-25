import { useEffect, useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { StepActionHeader } from "./StepActionHeader";
import { StageStepRow } from "./StageStepRow";
import { StageOutputsPanel } from "./StageOutputsPanel";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";
import { useActiveStageStep } from "../../hooks/useActiveStageStep";
import { useStageProgress } from "../../hooks/useStageProgress";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { firstTodoStepId } from "../../utils/resolveActiveStep";
import { scrollToStageStep } from "../../utils/activateStageStep";
import { stageNeedsPendingAction } from "../../utils/pendingAction";

export function StageStepWorkbench() {
  const {
    run,
    selectedStage,
    selectedStageId,
    activeStepId,
    setActiveStepId,
    selectStage,
    jobRunning,
    apiGrants,
    appendClientLog,
  } = useApp();

  const { fullyComplete } = useStageProgress(selectedStageId);

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
      }),
    [run, selectedStageId, jobRunning, apiGrants],
  );

  const stageAction = useStageOperatorAction(run, selectedStageId, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  const activeStep = useActiveStageStep(run, selectedStageId, activeStepId);

  const steps = selectedStage?.guidance?.steps ?? [];

  const stepEntry = nav.numberedStages.find((n) => n.stage.id === selectedStage?.id);

  const whatsNext = run?.journey?.next_action ?? null;

  useEffect(() => {
    if (!run || selectedStageId) return;
    const targetId = nav.currentStage?.id || nav.nextStage?.id;
    if (targetId) void selectStage(targetId);
  }, [run, selectedStageId, nav.currentStage?.id, nav.nextStage?.id, selectStage]);

  useEffect(() => {
    if (!selectedStageId || activeStepId) return;
    const first = firstTodoStepId(run, selectedStageId);
    if (first) setActiveStepId(first);
  }, [selectedStageId, activeStepId, run, setActiveStepId]);

  useEffect(() => {
    if (activeStepId) scrollToStageStep(activeStepId);
  }, [activeStepId, selectedStageId]);

  if (!selectedStage || !stageAction) {
    return (
      <div className="panel stage-step-workbench">
        <h2>Loading step…</h2>
      </div>
    );
  }

  const showDoneShell =
    fullyComplete &&
    !stageNeedsPendingAction(run!, selectedStage.id, apiGrants) &&
    steps.every((s) => s.status === "done");

  const activateStep = (stepId: string) => {
    setActiveStepId(stepId);
    const step = steps.find((s) => s.id === stepId);
    if (step) {
      appendClientLog(`Step ${step.number}: ${step.label}`, "info", selectedStage.id, stepId);
    }
    scrollToStageStep(stepId);
  };

  return (
    <div className={`panel stage-step-workbench${showDoneShell ? " stage-step-workbench--done" : ""}`}>
      <StepActionHeader
        action={stageAction}
        stepNumber={stepEntry?.number}
        whatsNext={whatsNext}
      />

      {showDoneShell ? (
        <div className="stage-detail-done-shell">
          <StepDoneBanner variant="step" />
          <StageOutputsPanel stage={selectedStage} />
        </div>
      ) : steps.length ? (
        <div className="stage-step-list">
          {steps.map((step) => (
            <StageStepRow
              key={step.id}
              step={step}
              stage={selectedStage}
              isActive={activeStep?.id === step.id}
              onActivate={() => activateStep(step.id)}
            />
          ))}
        </div>
      ) : (
        <p className="hint">No steps defined for this stage yet.</p>
      )}
    </div>
  );
}
