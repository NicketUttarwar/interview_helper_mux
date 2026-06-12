import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { firstTodoItem } from "../../utils/stageGuidance";
import { PHASE_LABELS } from "../../constants/phases";

export function PipelineCommandCenter() {
  const { run, selectedStageId, jobRunning, apiGrants } = useApp();

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

  const topTodo = nav.currentStage?.guidance
    ? firstTodoItem(nav.currentStage.guidance)
    : nav.nextStage?.guidance
      ? firstTodoItem(nav.nextStage.guidance)
      : null;

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
      </div>
    </section>
  );
}
