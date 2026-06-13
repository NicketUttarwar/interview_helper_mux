import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import {
  buildNumberedStages,
  resolvePipelineNav,
  stageNavStatus,
} from "../../utils/pipelineNavigation";
import { stageHasTodoActions } from "../../utils/stageGuidance";
import { ActionMarker } from "../guidance/ActionMarker";

export function PipelineStepList() {
  const { run, selectedStageId, selectStage, apiGrants, jobRunning, pinSelectedStage } = useApp();

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

  const numbered = buildNumberedStages(run.stages);

  return (
    <nav className="pipeline-step-list panel" aria-label="Numbered pipeline steps">
      <h3 className="pipeline-step-list-title">Steps</h3>
      <ol className="pipeline-steps">
        {numbered.map((entry) => {
          const status = stageNavStatus(entry, run, selectedStageId, nav.focusStageId);
          const isSelected = entry.stage.id === selectedStageId;
          const hasAction = stageHasTodoActions(entry.stage);
          const isRunning =
            jobRunning &&
            (run.job?.current_stage === entry.stage.id ||
              run.job?.stage === entry.stage.id);
          const navStatus = isRunning ? "running" : status;
          return (
            <li key={entry.stage.id}>
              <button
                type="button"
                className={`pipeline-step-row status-${navStatus}${isSelected ? " selected" : ""}${hasAction ? " has-action" : ""}${isRunning ? " running" : ""}`}
                onClick={() => {
                  pinSelectedStage();
                  void selectStage(entry.stage.id);
                }}
                aria-current={navStatus === "current" || isRunning ? "step" : undefined}
              >
                <span className="pipeline-step-num" aria-hidden>
                  {status === "done" ? "✓" : entry.number}
                </span>
                <span className="pipeline-step-body">
                  <span className="pipeline-step-title">
                    {hasAction ? (
                      <ActionMarker status="todo" className="pipeline-step-action-dot" />
                    ) : null}
                    {entry.stage.title}
                  </span>
                  <span className="pipeline-step-meta muted">
                    {entry.phaseLabel} · step {entry.number}
                    {entry.stage.status === "action_required"
                      ? " · needs you"
                      : entry.stage.status === "awaiting_write_approval"
                        ? " · review"
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
