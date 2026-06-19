import { Fragment, useMemo } from "react";
import { useApp } from "../../context/AppContext";
import {
  buildNumberedStages,
  resolvePipelineNav,
  stageNavStatus,
} from "../../utils/pipelineNavigation";
import { buildStageProgress, shouldShowRunningConnector } from "../../utils/stageSubsteps";
import { stageHasTodoActions } from "../../utils/stageGuidance";
import { stageNeedsAttention } from "../../utils/attentionQueue";
import { ActionMarker } from "../guidance/ActionMarker";
import { StepListContextHeader } from "./StepListContextHeader";
import { SubstepRow } from "./SubstepRow";
import { StepDoneBanner } from "./StepDoneBanner";
import { StepRunningConnector } from "./StepRunningConnector";

function stageNeedsSubstepAttention(
  run: NonNullable<ReturnType<typeof useApp>["run"]>,
  stageId: string,
  apiGrants: Record<string, boolean>,
  jobRunning: boolean,
  jobStageId?: string,
): boolean {
  const stage = run.stages.find((s) => s.id === stageId);
  if (!stage) return false;
  const progress = buildStageProgress(stage, run, { jobRunning, apiGrants });
  if (progress.hasTodo || progress.hasRunning) return true;
  if (jobRunning && jobStageId === stageId) return true;
  return stageNeedsAttention(run, stageId, apiGrants);
}

export function PipelineStepList() {
  const {
    run,
    selectedStageId,
    selectStage,
    apiGrants,
    jobRunning,
    actionBusy,
    pinSelectedStage,
    activateSubstep,
    activeSubstepId,
    pipelineCollapsedStages,
    pipelineExpandedDoneStages,
    toggleDoneStageExpanded,
    expandStage,
    pipelineFilterNeedsYou,
    setPipelineFilterNeedsYou,
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

  const numbered = buildNumberedStages(run.stages);
  const jobStageId = run.job?.current_stage || run.job?.stage;

  const filtered = pipelineFilterNeedsYou
    ? numbered.filter(
        (entry) =>
          stageNeedsSubstepAttention(run, entry.stage.id, apiGrants, jobRunning, jobStageId) ||
          entry.stage.id === nav.focusStageId,
      )
    : numbered;

  const toggleFilter = () => {
    setPipelineFilterNeedsYou(!pipelineFilterNeedsYou);
  };

  const isStageExpanded = (
    stageId: string,
    progress: ReturnType<typeof buildStageProgress>,
    navStatus: string,
  ): boolean => {
    if (pipelineCollapsedStages.includes(stageId)) return false;
    if (progress.fullyComplete) {
      return pipelineExpandedDoneStages.includes(stageId);
    }
    if (navStatus === "current" || navStatus === "blocked" || navStatus === "running") {
      return true;
    }
    if (progress.hasTodo || progress.hasRunning) return true;
    if (stageId === nav.focusStageId) return true;
    return stageId === selectedStageId;
  };

  return (
    <nav className="pipeline-step-list panel" aria-label="Numbered pipeline steps">
      <StepListContextHeader />
      <div className="pipeline-step-list-head">
        <h3 className="pipeline-step-list-title">Steps</h3>
        <button
          type="button"
          className={`btn ghost sm pipeline-step-list-filter${pipelineFilterNeedsYou ? " active" : ""}`}
          onClick={toggleFilter}
        >
          Needs you only
        </button>
      </div>
      {pipelineFilterNeedsYou && filtered.length === 0 ? (
        <p className="hint sm pipeline-step-filter-empty">
          Nothing matches — open the attention queue above or turn off the filter.
        </p>
      ) : null}
      <ol className="pipeline-steps">
        {filtered.map((entry, index) => {
          const status = stageNavStatus(entry, run, selectedStageId, nav.focusStageId);
          const isSelected = entry.stage.id === selectedStageId;
          const hasAction = stageHasTodoActions(entry.stage);
          const isRunning =
            jobRunning &&
            (run.job?.current_stage === entry.stage.id ||
              run.job?.stage === entry.stage.id);
          const navStatus = isRunning ? "running" : status;
          const progress = buildStageProgress(entry.stage, run, {
            jobRunning,
            actionBusy,
            apiGrants,
          });
          const expanded = isStageExpanded(entry.stage.id, progress, navStatus);
          const nextEntry = filtered[index + 1];
          const showConnector =
            nextEntry &&
            shouldShowRunningConnector(
              entry.stage,
              nextEntry.stage,
              run,
              jobRunning,
              actionBusy,
            );

          return (
            <Fragment key={entry.stage.id}>
              <li className="pipeline-step-item">
                <div
                  className={`pipeline-step-row-wrap${progress.fullyComplete ? " fully-done" : ""}${progress.fullyComplete && !expanded ? " collapsed" : ""}`}
                >
                  <button
                    type="button"
                    className={`pipeline-step-row status-${navStatus}${isSelected ? " selected" : ""}${hasAction ? " has-action" : ""}${isRunning ? " running" : ""}${progress.fullyComplete ? " fully-done" : ""}`}
                    data-testid={`pipeline-step-${entry.stage.id}`}
                    onClick={() => {
                      if (progress.fullyComplete) {
                        toggleDoneStageExpanded(entry.stage.id);
                        return;
                      }
                      pinSelectedStage();
                      expandStage(entry.stage.id);
                      void selectStage(entry.stage.id);
                    }}
                    aria-current={navStatus === "current" || isRunning ? "step" : undefined}
                    aria-expanded={expanded}
                  >
                    <span className="pipeline-step-num" aria-hidden>
                      {status === "done" ? "✓" : entry.number}
                    </span>
                    <span className="pipeline-step-body">
                      <span className="pipeline-step-title">
                        {hasAction ? (
                          <ActionMarker status="todo" className="pipeline-step-action-dot" />
                        ) : null}
                        {isRunning ? (
                          <span className="spinner-inline pipeline-step-title-spinner" aria-hidden />
                        ) : null}
                        {entry.stage.title}
                      </span>
                      <span className="pipeline-step-meta muted">
                        {entry.phaseLabel} · step {entry.number}
                        {progress.activeSubstep && (expanded || isSelected)
                          ? ` · ${progress.activeSubstep.label}`
                          : entry.stage.status === "action_required"
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
                  {progress.fullyComplete && !expanded ? (
                    <StepDoneBanner variant="step" />
                  ) : null}
                  {expanded && progress.substeps.length > 0 ? (
                    <ul className="pipeline-substeps" aria-label={`${entry.stage.title} substeps`}>
                      {progress.substeps.map((sub) => (
                        <li key={`${sub.kind}:${sub.id}`}>
                          <SubstepRow
                            substep={sub}
                            selected={activeSubstepId === sub.id}
                            onClick={() => activateSubstep(sub)}
                          />
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </li>
              {showConnector ? (
                <StepRunningConnector
                  label={
                    isRunning
                      ? `Running ${entry.stage.title}…`
                      : `Running ${nextEntry?.stage.title ?? "pipeline"}…`
                  }
                />
              ) : null}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
