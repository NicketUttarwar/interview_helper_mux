import { useEffect, useMemo, useRef } from "react";
import { useApp } from "../../context/AppContext";
import { StepActionHeader } from "./StepActionHeader";
import { StageStepRow } from "./StageStepRow";
import { StageOutputsPanel } from "./StageOutputsPanel";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";
import { useStageOperatorAction } from "../../hooks/useOperatorAction";
import { useActiveStageStep } from "../../hooks/useActiveStageStep";
import { useStageProgress } from "../../hooks/useStageProgress";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { resolveFocusStepId, shouldAdvanceStaleStep } from "../../utils/resolveActiveStep";
import { scrollToStageStep } from "../../utils/activateStageStep";
import { stageNeedsPendingAction } from "../../utils/pendingAction";
import { StageReuseSection } from "../guidance/StageReuseSection";
import { StageReviewGateBanner } from "../gates/StageReviewGateBanner";
import { resolveReviewGateSpec } from "../../utils/resolveReviewGate";
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
    autoContinuePipeline,
    syncPipelineStageFocus,
    config,
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

  const prevStageIdRef = useRef<string | null>(null);
  const userReviewingCompletedRef = useRef(false);

  useEffect(() => {
    if (!run || selectedStageId) return;
    const targetId = nav.currentStage?.id || nav.nextStage?.id;
    if (targetId) void selectStage(targetId);
  }, [run, selectedStageId, nav.currentStage?.id, nav.nextStage?.id, selectStage]);

  useEffect(() => {
    if (!selectedStageId) return;
    const stageChanged = prevStageIdRef.current !== selectedStageId;
    prevStageIdRef.current = selectedStageId;
    if (!stageChanged) return;
    userReviewingCompletedRef.current = false;
    if (activeStepId) return;
    const first = resolveFocusStepId(run, selectedStageId);
    if (first) setActiveStepId(first);
  }, [selectedStageId, activeStepId, run, setActiveStepId]);

  useEffect(() => {
    if (!run || !selectedStageId || !activeStepId) return;
    const next = shouldAdvanceStaleStep(run, selectedStageId, activeStepId, {
      userReviewingCompletedStep: userReviewingCompletedRef.current,
    });
    if (next) {
      userReviewingCompletedRef.current = false;
      setActiveStepId(next);
    }
  }, [run, selectedStageId, activeStepId, setActiveStepId]);

  useEffect(() => {
    if (activeStepId) scrollToStageStep(activeStepId);
  }, [activeStepId, selectedStageId]);

  const stageReadyToAdvance =
    Boolean(selectedStage) &&
    selectedStage!.status === "done" &&
    !stageNeedsPendingAction(run!, selectedStage!.id, apiGrants) &&
    !jobRunning;

  const showDoneShell =
    Boolean(selectedStage) &&
    fullyComplete &&
    stageReadyToAdvance &&
    steps.every((s) => s.status === "done");

  useEffect(() => {
    if (!stageReadyToAdvance || !run || !selectedStageId || jobRunning) return;
    // Execute completion is chained from job poll; avoid a second auto-continue burst.
    const jobStatus = run.job?.status;
    if (jobStatus === "complete" || jobStatus === "error") return;
    void (async () => {
      await syncPipelineStageFocus();
      await autoContinuePipeline(selectedStageId);
    })();
  }, [stageReadyToAdvance, run, selectedStageId, jobRunning, syncPipelineStageFocus, autoContinuePipeline]);

  if (!selectedStage || !stageAction) {
    return (
      <div className="panel stage-step-workbench">
        <h2>Loading step…</h2>
      </div>
    );
  }

  const reviewGateSpec = resolveReviewGateSpec(run ?? null, selectedStage, showDoneShell, config);

  const activateStep = (stepId: string) => {
    const step = steps.find((s) => s.id === stepId);
    userReviewingCompletedRef.current =
      step?.status === "done" || step?.status === "waiting";
    setActiveStepId(stepId);
    if (step) {
      appendClientLog(`Step ${step.number}: ${step.label}`, "info", selectedStage.id, stepId);
    }
    scrollToStageStep(stepId);
  };

  const reviewDetailStepId =
    reviewGateSpec?.kind === "transcript_review"
      ? "listen_clips"
      : reviewGateSpec?.kind === "disfluency_review"
        ? "review_fillers"
        : undefined;

  return (
    <div className={`panel stage-step-workbench${showDoneShell ? " stage-step-workbench--done" : ""}`}>
      <StepActionHeader
        action={stageAction}
        stepNumber={stepEntry?.number}
        whatsNext={whatsNext}
      />

      {reviewGateSpec ? (
        <StageReviewGateBanner
          spec={reviewGateSpec}
          stage={selectedStage}
          onReviewDetail={
            reviewDetailStepId
              ? () => activateStep(reviewDetailStepId)
              : undefined
          }
        />
      ) : null}

      {!showDoneShell ? <StageReuseSection stage={selectedStage} /> : null}

      {showDoneShell ? (
        <div className="stage-detail-done-shell">
          <StepDoneBanner variant="step" />
          <StageOutputsPanel stage={selectedStage} />
        </div>
      ) : steps.length ? (
        <div className="stage-step-list-wrap">
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
        </div>
      ) : (
        <p className="hint">No steps defined for this stage yet.</p>
      )}
    </div>
  );
}
