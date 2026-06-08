import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { PhaseGuidanceBanner } from "../guidance/PhaseGuidanceBanner";
import { firstTodoItem } from "../../utils/stageGuidance";

export function PipelineCommandCenter() {
  const {
    run,
    selectedStageId,
    jobRunning,
    runNextStage,
    openActionModal,
    acknowledgeHandoff,
    selectStage,
    apiGrants,
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

  const onPrimary = () => {
    if (nav.primaryAction === "handoff") {
      void acknowledgeHandoff();
      return;
    }
    if (nav.primaryAction === "checkpoint") {
      if (nav.focusStageId) void selectStage(nav.focusStageId);
      openActionModal();
      return;
    }
    if (nav.primaryAction === "run_next") {
      if (nav.nextStage) void selectStage(nav.nextStage.id);
      void runNextStage();
    }
  };

  const primaryLabel =
    nav.primaryAction === "handoff"
      ? "Acknowledge & continue"
      : nav.primaryAction === "checkpoint"
        ? "Open checkpoint"
        : nav.primaryAction === "run_next"
          ? jobRunning
            ? "Running…"
            : `Run step ${nav.nextNumber ?? ""}`.trim()
          : null;

  const topTodo = nav.currentStage?.guidance
    ? firstTodoItem(nav.currentStage.guidance)
    : nav.nextStage?.guidance
      ? firstTodoItem(nav.nextStage.guidance)
      : null;

  return (
    <section className="pipeline-command-center panel" aria-label="Pipeline progress">
      {run ? <PhaseGuidanceBanner run={run} /> : null}
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
          {topTodo ? (
            <p className="hint pipeline-command-next">
              <span className="action-marker status-todo" aria-hidden>
                ●
              </span>{" "}
              {topTodo.label}
            </p>
          ) : nav.nextLine ? (
            <p className="hint pipeline-command-next">{nav.nextLine}</p>
          ) : null}
        </div>
        <div className="pipeline-command-actions">
          {primaryLabel ? (
            <button
              type="button"
              className="btn primary"
              data-testid="pipeline-primary-action"
              disabled={!nav.canRunNext || jobRunning}
              onClick={onPrimary}
            >
              {primaryLabel}
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
