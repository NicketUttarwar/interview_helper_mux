import { Fragment, useMemo, useCallback, type KeyboardEvent } from "react";
import { useApp } from "../../context/AppContext";
import { useGlobalOperatorAction } from "../../hooks/useOperatorAction";
import {
  buildNumberedStages,
  resolvePipelineNav,
  stageNavStatus,
} from "../../utils/pipelineNavigation";
import { buildStageProgress, shouldShowRunningConnector } from "../../utils/stageSubsteps";
import { stageHasTodoActions } from "../../utils/stageGuidance";
import { isOptionalStageSkipped } from "../../utils/preclean";
import { stageNeedsAttention } from "../../utils/attentionQueue";
import { firstUpstreamBlocker } from "../../utils/stageOutputs";
import { isJobActivelyRunning } from "../../utils/jobStatus";
import { ActionMarker } from "../guidance/ActionMarker";
import { StepListContextHeader } from "./StepListContextHeader";
import { StepDoneBanner } from "./StepDoneBanner";
import { StepRunningConnector } from "./StepRunningConnector";
import { resolveFocusStepId } from "../../utils/resolveActiveStep";
import { stageHadAutoNavigation } from "../../utils/autoNavigationLedger";

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
    pipelineCollapsedStages,
    pipelineExpandedDoneStages,
    toggleDoneStageExpanded,
    expandStage,
    pipelineFilterNeedsYou,
    setPipelineFilterNeedsYou,
    isStagePinned,
    showToast,
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

  const operatorAction = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  const focusStageId =
    operatorAction.mode === "needs_you" && operatorAction.stageId
      ? operatorAction.stageId
      : nav.focusStageId;

  const onStepsKeyDown = useCallback(
    (e: KeyboardEvent<HTMLOListElement>) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const rows = Array.from(
        e.currentTarget.querySelectorAll<HTMLButtonElement>("button.pipeline-step-row"),
      );
      if (!rows.length) return;
      const current = rows.findIndex((r) => r === document.activeElement);
      const next =
        e.key === "ArrowDown"
          ? Math.min(rows.length - 1, current < 0 ? 0 : current + 1)
          : Math.max(0, current <= 0 ? 0 : current - 1);
      e.preventDefault();
      rows[next]?.focus();
    },
    [],
  );

  if (!run) return null;

  const numbered = buildNumberedStages(run.stages);
  const jobStageId = run.job?.current_stage || run.job?.stage;

  const filtered = pipelineFilterNeedsYou
    ? numbered.filter(
        (entry) =>
          stageNeedsSubstepAttention(run, entry.stage.id, apiGrants, jobRunning, jobStageId) ||
          entry.stage.id === focusStageId,
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
    if (stageId === focusStageId) return true;
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
      <ol className="pipeline-steps" onKeyDown={onStepsKeyDown}>
        {filtered.map((entry, index) => {
          const status = stageNavStatus(entry, run, selectedStageId, focusStageId);
          const isSelected = entry.stage.id === selectedStageId;
          const isFocus =
            entry.stage.id === focusStageId && operatorAction.mode === "needs_you";
          const hasAction = stageHasTodoActions(entry.stage, run.meta);
          const isRunning =
            (jobRunning || isJobActivelyRunning(run.job)) &&
            (run.job?.current_stage === entry.stage.id ||
              run.job?.stage === entry.stage.id);
          const isError =
            run.job?.status === "error" &&
            (run.job?.stage === entry.stage.id ||
              run.job?.current_stage === entry.stage.id);
          const navStatus = isRunning ? "running" : isError ? "error" : status;
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

          const skippedOptional = isOptionalStageSkipped(entry.stage, run.meta);
          const skipped = skippedOptional;
          const upstreamBlocker = firstUpstreamBlocker(run.stages, entry.stage.id, run.meta);
          const metaSuffix = skipped
            ? " · skipped"
            : isError
              ? " · failed"
              : isRunning
              ? " · running"
              : progress.hasTodo || entry.stage.id === focusStageId
                ? " · your turn"
                : entry.stage.status === "awaiting_write_approval"
                  ? " · review"
                  : entry.stage.status === "locked"
                    ? " · locked"
                    : entry.stage.status === "done"
                      ? " · done"
                      : "";

          return (
            <Fragment key={entry.stage.id}>
              <li className="pipeline-step-item">
                <div
                  className={`pipeline-step-row-wrap${progress.fullyComplete ? " fully-done" : ""}${progress.fullyComplete && !expanded ? " collapsed" : ""}`}
                >
                  <button
                    type="button"
                    tabIndex={isSelected || isFocus ? 0 : -1}
                    className={`pipeline-step-row status-${navStatus}${isSelected ? " selected" : ""}${isFocus ? " sidebar-step--focus" : ""}${isError ? " sidebar-step--error" : ""}${hasAction ? " has-action" : ""}${isRunning ? " running" : ""}${progress.fullyComplete ? " fully-done" : ""}${skipped ? " status-skipped" : ""}`}
                    data-testid={`pipeline-step-${entry.stage.id}`}
                    onClick={() => {
                      if (skipped) {
                        showToast("Optional step skipped — not required for this run.");
                        return;
                      }
                      if (progress.fullyComplete) {
                        toggleDoneStageExpanded(entry.stage.id);
                        return;
                      }
                      pinSelectedStage();
                      expandStage(entry.stage.id);
                      void selectStage(entry.stage.id, {
                        stepId: resolveFocusStepId(run, entry.stage.id),
                      });
                    }}
                    aria-current={navStatus === "current" || isRunning ? "step" : undefined}
                    aria-expanded={expanded}
                    aria-disabled={skipped || undefined}
                  >
                    <span className="pipeline-step-num" aria-hidden>
                      {status === "done" || skipped ? "✓" : entry.number}
                    </span>
                    <span className="pipeline-step-body">
                      <span className="pipeline-step-title">
                        {hasAction && !skipped ? (
                          <ActionMarker status="todo" className="pipeline-step-action-dot" />
                        ) : null}
                        {isRunning ? (
                          <span className="spinner-inline pipeline-step-title-spinner" aria-hidden />
                        ) : null}
                        {entry.stage.title}
                        {isSelected && isStagePinned ? (
                          <span
                            className="pipeline-step-pin muted"
                            title="Browsing away from the guided stage — auto-redirect will not pull you back"
                            aria-label="Stage pinned"
                          >
                            📌
                          </span>
                        ) : null}
                      </span>
                      <span className="pipeline-step-meta muted">
                        {entry.phaseLabel} · step {entry.number}
                        {upstreamBlocker ? (
                          <span className="pipeline-step-blocked-chip" title={`Blocked by ${upstreamBlocker.title}`}>
                            {" "}
                            · Blocked by {upstreamBlocker.title}
                          </span>
                        ) : null}
                        {stageHadAutoNavigation(entry.stage.id) ? " · guided" : ""}
                        {metaSuffix}
                        {progress.activeSubstep && (expanded || isSelected) && !metaSuffix
                          ? ` · ${progress.activeSubstep.label}`
                          : ""}
                      </span>
                    </span>
                  </button>
                  {progress.fullyComplete && !expanded ? (
                    <StepDoneBanner variant="step" />
                  ) : null}
                </div>
              </li>
              {showConnector ? (
                <StepRunningConnector
                  stepIndex={
                    isRunning && run.job?.step_total
                      ? run.job?.step_index ?? null
                      : run.job?.stage_index ?? entry.number
                  }
                  stepTotal={
                    isRunning && run.job?.step_total
                      ? run.job?.step_total
                      : run.job?.stage_total ?? numbered.length
                  }
                  label={
                    isRunning && run.job?.message
                      ? run.job.message
                      : isRunning
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
