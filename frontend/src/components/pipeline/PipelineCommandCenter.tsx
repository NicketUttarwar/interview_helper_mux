import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { firstTodoItem } from "../../utils/stageGuidance";
import { resolveStagePrimaryAction } from "../../utils/stagePrimaryAction";
import { resolvePrecleanOffer } from "../../utils/preclean";
import { PHASE_LABELS } from "../../constants/phases";

export function PipelineCommandCenter() {
  const {
    run,
    selectedStageId,
    selectedStage,
    jobRunning,
    apiGrants,
    sessionReady,
    selectStage,
    openActionModal,
    acknowledgeHandoff,
    executeJob,
    runNextStage,
  } = useApp();

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
      }),
    [run, selectedStageId, jobRunning, apiGrants],
  );

  if (!run) return null;

  const phase = run.journey?.phase ?? run.meta?.operator_phase ?? "prepare";
  const phaseGoal =
    run.journey?.phase_guidance?.[phase]?.goal ||
    PHASE_LABELS[phase] ||
    "";

  const actionStage = selectedStage || nav.nextStage || nav.currentStage;
  const topTodo = actionStage?.guidance ? firstTodoItem(actionStage.guidance) : null;

  const headerAction = useMemo(() => {
    if (!actionStage) return null;
    const offer = resolvePrecleanOffer(actionStage, run.meta);
    return resolveStagePrimaryAction(actionStage, run, nav, {
      jobRunning,
      hasPrecleanOffer: Boolean(offer),
    });
  }, [actionStage, run, nav, jobRunning]);

  const onHeaderClick = () => {
    if (!headerAction || headerAction.disabled) return;
    switch (headerAction.kind) {
      case "run":
        if (headerAction.targetStageId && headerAction.targetStageId !== actionStage?.id) {
          void selectStage(headerAction.targetStageId).then(() => {
            if (headerAction.runStageId === nav.nextStage?.id) void runNextStage();
            else if (headerAction.runStageId) {
              void executeJob({ mode: "stage", stage: headerAction.runStageId });
            }
          });
          return;
        }
        if (headerAction.runStageId === nav.nextStage?.id) void runNextStage();
        else if (headerAction.runStageId) {
          void executeJob({ mode: "stage", stage: headerAction.runStageId });
        } else void runNextStage();
        return;
      case "checkpoint":
        if (headerAction.targetStageId) void selectStage(headerAction.targetStageId);
        openActionModal();
        return;
      case "handoff":
        void acknowledgeHandoff();
        return;
      case "navigate":
        if (headerAction.targetStageId) void selectStage(headerAction.targetStageId);
        return;
      default:
        return;
    }
  };

  const showHeaderBtn =
    headerAction &&
    !jobRunning &&
    (headerAction.kind === "run" ||
      headerAction.kind === "checkpoint" ||
      headerAction.kind === "handoff" ||
      headerAction.kind === "navigate");

  return (
    <section className="pipeline-command-center panel" aria-label="Pipeline progress">
      <div className="pipeline-command-head">
        <div>
          <p className="pipeline-command-eyebrow">
            {nav.currentNumber
              ? `Pipeline step ${nav.currentNumber} of ${nav.numberedStages.length}${
                  nav.currentStage?.guidance?.phase_label
                    ? ` · ${nav.currentStage.guidance.phase_label} phase`
                    : ""
                }`
              : `Pipeline · ${nav.numberedStages.length} steps`}
          </p>
          <h2 className="pipeline-command-title">
            {nav.currentStage?.title || nav.nextStage?.title || "Pipeline"}
          </h2>
          <p className="pipeline-command-status">{nav.statusLine}</p>
          {phaseGoal ? (
            <p className="hint sm pipeline-command-phase-goal">{phaseGoal}</p>
          ) : null}
          {topTodo && !showHeaderBtn ? (
            <p className="hint pipeline-command-next">
              <span className="action-marker status-todo" aria-hidden>
                ●
              </span>{" "}
              {topTodo.label}
            </p>
          ) : nav.nextLine && !showHeaderBtn ? (
            <p className="hint pipeline-command-next">{nav.nextLine}</p>
          ) : null}
        </div>
        {showHeaderBtn && headerAction ? (
          <div className="pipeline-command-actions">
            <button
              type="button"
              className="btn primary"
              disabled={headerAction.disabled || !sessionReady}
              data-testid="pipeline-command-primary"
              onClick={onHeaderClick}
            >
              {headerAction.label}
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
