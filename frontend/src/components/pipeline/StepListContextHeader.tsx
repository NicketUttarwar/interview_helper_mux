import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { PHASE_LABELS } from "../../constants/phases";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { buildPhaseSubsteps } from "../../utils/phaseSubsteps";
import { useStageProgress } from "../../hooks/useStageProgress";

export function StepListContextHeader() {
  const { run, selectedStageId, jobRunning, apiGrants } = useApp();
  const { activeSubstepGlobal } = useStageProgress();

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
  const phaseSummary = buildPhaseSubsteps(run, phase, {
    jobRunning,
    apiGrants,
    selectedStageId,
  });

  const youAreHere =
    activeSubstepGlobal?.label ||
    nav.currentStage?.title ||
    nav.focusStageId
      ? run.stages.find((s) => s.id === nav.focusStageId)?.title
      : null;

  const nextTitle = nav.nextStage?.title;

  return (
    <header className="pipeline-step-list-context" id="pipeline-step-context">
      <p className="pipeline-step-context-phase">
        <strong>{PHASE_LABELS[phase] || phase}</strong> phase
        {phaseSummary.stagesTotal > 0 ? (
          <span className="muted">
            {" "}
            · {phaseSummary.stagesDone}/{phaseSummary.stagesTotal} steps done
          </span>
        ) : null}
      </p>
      {youAreHere ? (
        <p className="pipeline-step-context-here hint sm">
          You are here: <strong>{youAreHere}</strong>
        </p>
      ) : null}
      {nextTitle && !run.journey?.blocking?.blocked ? (
        <p className="pipeline-step-context-next hint sm">
          Next: <strong>{nextTitle}</strong>
        </p>
      ) : null}
      {run.journey?.blocking?.blocked && run.journey.blocking.message ? (
        <p className="pipeline-step-context-blocked warning sm">
          {run.journey.blocking.message}
        </p>
      ) : null}
    </header>
  );
}
