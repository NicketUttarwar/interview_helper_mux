import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { ALL_API_CONSENTS } from "../../utils";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";

export function PipelineCommandCenter() {
  const {
    run,
    runId,
    config,
    selectedStageId,
    jobRunning,
    runNextStage,
    openActionModal,
    acknowledgeHandoff,
    refreshRun,
    startJobPoll,
    showToast,
    selectStage,
  } = useApp();

  const nav = useMemo(
    () =>
      resolvePipelineNav(run, {
        selectedStageId,
        jobRunning,
        apiGrants: ALL_API_CONSENTS,
        pauseSecondsDefault: config?.journey_ui?.step_through_pause_seconds ?? 10,
      }),
    [run, selectedStageId, jobRunning, config],
  );

  const [secondsLeft, setSecondsLeft] = useState(nav.stepThroughSeconds);
  const [submitting, setSubmitting] = useState(false);
  const autoFiredRef = useRef(false);

  useEffect(() => {
    setSecondsLeft(nav.stepThroughSeconds);
    autoFiredRef.current = false;
  }, [nav.stepThroughStageId, nav.stepThroughSeconds]);

  const submitStepThrough = useCallback(
    async (action: "proceed" | "skip") => {
      if (!runId || !nav.stepThroughStageId || submitting) return;
      setSubmitting(true);
      try {
        const res = await api<{ ok?: boolean; error?: string }>(
          `/api/runs/${runId}/stage-transition`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              stage_id: nav.stepThroughStageId,
              action,
              api_consents: ALL_API_CONSENTS,
            }),
          },
        );
        if (res.ok === false) {
          showToast(res.error || "Could not continue");
          await refreshRun();
          return;
        }
        startJobPoll();
        await refreshRun();
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Could not continue");
      } finally {
        setSubmitting(false);
      }
    },
    [
      runId,
      nav.stepThroughStageId,
      submitting,
      showToast,
      refreshRun,
      startJobPoll,
    ],
  );

  useEffect(() => {
    if (!nav.stepThroughStageId || jobRunning) return;
    if (secondsLeft <= 0) {
      if (!autoFiredRef.current) {
        autoFiredRef.current = true;
        void submitStepThrough("proceed");
      }
      return;
    }
    const t = window.setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [nav.stepThroughStageId, secondsLeft, jobRunning, submitStepThrough]);

  if (!run) return null;

  const onPrimary = () => {
    if (nav.primaryAction === "handoff") {
      void acknowledgeHandoff();
      return;
    }
    if (nav.primaryAction === "step_through_proceed") {
      void submitStepThrough("proceed");
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
      : nav.primaryAction === "step_through_proceed"
        ? submitting
          ? "Starting…"
          : "Run this step"
        : nav.primaryAction === "checkpoint"
          ? "Open checkpoint"
          : nav.primaryAction === "run_next"
            ? jobRunning
              ? "Running…"
              : `Run step ${nav.nextNumber ?? ""}`.trim()
            : null;

  return (
    <section className="pipeline-command-center panel" aria-label="Pipeline progress">
      <div className="pipeline-command-head">
        <div>
          <p className="pipeline-command-eyebrow">
            {nav.currentNumber
              ? `You are on step ${nav.currentNumber} of ${nav.numberedStages.length}`
              : `Pipeline · ${nav.numberedStages.length} steps`}
          </p>
          <h2 className="pipeline-command-title">
            {nav.currentStage?.title || nav.nextStage?.title || "Pipeline"}
          </h2>
          <p className="pipeline-command-status">{nav.statusLine}</p>
          {nav.nextLine ? <p className="hint pipeline-command-next">{nav.nextLine}</p> : null}
        </div>
        <div className="pipeline-command-actions">
          {nav.canSkipStepThrough ? (
            <button
              type="button"
              className="btn ghost"
              data-testid="pipeline-skip-step"
              disabled={submitting || jobRunning}
              onClick={() => void submitStepThrough("skip")}
            >
              Skip this step
            </button>
          ) : null}
          {primaryLabel ? (
            <button
              type="button"
              className="btn primary"
              data-testid="pipeline-primary-action"
              disabled={!nav.canRunNext || jobRunning || submitting}
              onClick={onPrimary}
            >
              {primaryLabel}
            </button>
          ) : null}
        </div>
      </div>

      {nav.stepThroughStageId && !jobRunning ? (
        <div className="pipeline-step-through-banner" data-testid="pipeline-step-through">
          <span>
            Step-through pause — auto-runs in <strong>{secondsLeft}s</strong>
          </span>
          <div className="pipeline-step-through-buttons">
            <button
              type="button"
              className="btn ghost sm"
              disabled={submitting}
              onClick={() => void submitStepThrough("skip")}
            >
              Skip step
            </button>
            <button
              type="button"
              className="btn primary sm"
              disabled={submitting}
              onClick={() => void submitStepThrough("proceed")}
            >
              Proceed now
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
