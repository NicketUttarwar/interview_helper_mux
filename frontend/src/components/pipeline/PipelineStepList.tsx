import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import {
  buildNumberedStages,
  resolvePipelineNav,
  stageNavStatus,
} from "../../utils/pipelineNavigation";

export function PipelineStepList() {
  const { run, selectedStageId, selectStage, apiGrants, jobRunning, config } = useApp();

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants,
        pauseSecondsDefault: config?.journey_ui?.step_through_pause_seconds ?? 10,
      }),
    [run, selectedStageId, jobRunning, apiGrants, config],
  );

  if (!run) return null;

  const numbered = buildNumberedStages(run.stages);

  return (
    <nav className="pipeline-step-list panel" aria-label="Numbered pipeline steps">
      <h3 className="pipeline-step-list-title">Steps</h3>
      <ol className="pipeline-steps">
        {numbered.map((entry) => {
          const status = stageNavStatus(entry, run, selectedStageId, nav.focusStageId);
          const isSelected = entry.stage.id === selectedStageId;
          return (
            <li key={entry.stage.id}>
              <button
                type="button"
                className={`pipeline-step-row status-${status}${isSelected ? " selected" : ""}`}
                onClick={() => void selectStage(entry.stage.id)}
                aria-current={status === "current" ? "step" : undefined}
              >
                <span className="pipeline-step-num" aria-hidden>
                  {status === "done" ? "✓" : entry.number}
                </span>
                <span className="pipeline-step-body">
                  <span className="pipeline-step-title">{entry.stage.title}</span>
                  <span className="pipeline-step-meta muted">
                    {entry.phaseLabel}
                    {entry.stage.status === "action_required"
                      ? " · needs you"
                      : entry.stage.status === "locked"
                        ? " · locked"
                        : entry.stage.status === "done"
                          ? " · done"
                          : status === "current"
                            ? " · current"
                            : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
