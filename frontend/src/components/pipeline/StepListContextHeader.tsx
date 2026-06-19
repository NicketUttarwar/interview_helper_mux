import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { PHASE_LABELS } from "../../constants/phases";
import { buildNumberedStages, resolvePipelineNav } from "../../utils/pipelineNavigation";
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

  const numbered = buildNumberedStages(run.stages);
  const focusEntry = nav.focusStageId
    ? numbered.find((n) => n.stage.id === nav.focusStageId)
    : null;
  const focusTitle = focusEntry
    ? `Step ${focusEntry.number} — ${focusEntry.stage.title}`
    : nav.currentStage?.title;

  const jobStageId = run.job?.current_stage || run.job?.stage;
  const waitingOnJob =
    jobRunning && jobStageId
      ? run.stages.find((s) => s.id === jobStageId)?.title
      : null;

  const userActionPending =
    activeSubstepGlobal?.status === "todo" &&
    activeSubstepGlobal.kind !== "run";

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
      {focusTitle ? (
        <p className="pipeline-step-context-here hint sm">
          You are here: <strong>{focusTitle}</strong>
        </p>
      ) : null}
      {waitingOnJob ? (
        <p className="pipeline-step-context-waiting hint sm">
          <span className="spinner-inline" aria-hidden /> Waiting: Running {waitingOnJob}…
        </p>
      ) : userActionPending && activeSubstepGlobal ? (
        <p className="pipeline-step-context-action hint sm">
          Current action: <strong>{activeSubstepGlobal.label}</strong>
        </p>
      ) : null}
      {nav.nextStage?.title && !userActionPending && !waitingOnJob ? (
        <p className="pipeline-step-context-next hint sm">
          Next after this: <strong>{nav.nextStage.title}</strong>
        </p>
      ) : null}
    </header>
  );
}
