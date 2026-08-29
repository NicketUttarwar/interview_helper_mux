import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { PHASE_LABELS } from "../../constants/phases";
import { buildPhaseSubsteps } from "../../utils/phaseSubsteps";
import { useGlobalOperatorAction } from "../../hooks/useOperatorAction";
import { buildNumberedStages } from "../../utils/pipelineNavigation";

export function StepListContextHeader() {
  const { run, selectedStageId, jobRunning, apiGrants, partialAutoGPublish } = useApp();

  const action = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
    gPublish: partialAutoGPublish,
  });

  const phaseSummary = useMemo(() => {
    if (!run) return null;
    const phase = run.journey?.phase ?? run.meta?.operator_phase ?? "prepare";
    return buildPhaseSubsteps(run, phase, {
      jobRunning,
      apiGrants,
      selectedStageId,
    });
  }, [run, jobRunning, apiGrants, selectedStageId]);

  if (!run) return null;

  const phase = run.journey?.phase ?? run.meta?.operator_phase ?? "prepare";
  const numbered = buildNumberedStages(run.stages);
  const focusEntry = action.stageId
    ? numbered.find((n) => n.stage.id === action.stageId)
    : null;

  let contextLine: string | null = null;
  if (action.mode === "running" && action.stageId) {
    contextLine = `Running ${focusEntry?.stage.title ?? action.stageId}…`;
  } else if (action.mode === "needs_you" && focusEntry) {
    contextLine = `Step ${focusEntry.number} — ${focusEntry.stage.title} · Needs you`;
  } else if (focusEntry && action.mode !== "idle") {
    contextLine = `Step ${focusEntry.number} — ${focusEntry.stage.title}`;
  } else if (action.subline) {
    contextLine = action.subline;
  }

  return (
    <header className="pipeline-step-list-context" id="pipeline-step-context">
      <p className="pipeline-step-context-phase">
        <strong>{PHASE_LABELS[phase] || phase}</strong> phase
        {phaseSummary && phaseSummary.stagesTotal > 0 ? (
          <span className="muted">
            {" "}
            · {phaseSummary.stagesDone}/{phaseSummary.stagesTotal} steps done
          </span>
        ) : null}
      </p>
      {contextLine ? (
        <p className="pipeline-step-context-action hint sm">{contextLine}</p>
      ) : null}
    </header>
  );
}
