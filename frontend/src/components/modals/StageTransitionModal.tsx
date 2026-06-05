import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

export function StageTransitionModal() {
  const { run, runId, config, showToast, refreshRun, startJobPoll, apiGrants } = useApp();

  const job = run?.job;
  const pendingMeta = run?.meta?.step_through?.pending;
  const stageId = job?.stage || pendingMeta?.stage_id || null;
  const stageTitle = useMemo(() => {
    if (!run || !stageId) return "Next step";
    return run.stages.find((s) => s.id === stageId)?.title || pendingMeta?.title || stageId;
  }, [run, stageId, pendingMeta?.title]);

  const pauseSeconds = useMemo(() => {
    const fromJob = job?.pause_seconds;
    if (typeof fromJob === "number" && fromJob > 0) return fromJob;
    const fromMeta = pendingMeta?.pause_seconds;
    if (typeof fromMeta === "number" && fromMeta > 0) return fromMeta;
    const fromConfig = config?.journey_ui?.step_through_pause_seconds;
    if (typeof fromConfig === "number" && fromConfig > 0) return fromConfig;
    return 10;
  }, [job?.pause_seconds, pendingMeta?.pause_seconds, config?.journey_ui?.step_through_pause_seconds]);

  const [secondsLeft, setSecondsLeft] = useState(pauseSeconds);
  const [submitting, setSubmitting] = useState(false);
  const autoFiredRef = useRef(false);

  useEffect(() => {
    setSecondsLeft(pauseSeconds);
    autoFiredRef.current = false;
  }, [stageId, pauseSeconds]);

  const submit = useCallback(
    async (action: "proceed" | "skip") => {
      if (!runId || !stageId || submitting) return;
      setSubmitting(true);
      try {
        const api_consents: Record<string, boolean> = {};
        for (const [k, v] of Object.entries(apiGrants)) {
          if (v) api_consents[k] = true;
        }
        const res = await api<{ ok?: boolean; error?: string }>(
          `/api/runs/${runId}/stage-transition`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ stage_id: stageId, action, api_consents }),
          },
        );
        if (res.ok === false) {
          showToast(res.error || "Could not continue pipeline");
          await refreshRun();
          return;
        }
        startJobPoll();
        await refreshRun();
      } catch (e) {
        showToast(e instanceof Error ? e.message : "Could not continue pipeline");
      } finally {
        setSubmitting(false);
      }
    },
    [runId, stageId, submitting, apiGrants, showToast, refreshRun, startJobPoll],
  );

  useEffect(() => {
    if (job?.status !== "stage_transition" || !stageId) return;
    if (secondsLeft <= 0) {
      if (!autoFiredRef.current) {
        autoFiredRef.current = true;
        void submit("proceed");
      }
      return;
    }
    const timer = window.setTimeout(() => {
      setSecondsLeft((s) => s - 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [job?.status, stageId, secondsLeft, submit]);

  if (job?.status !== "stage_transition" || !stageId) return null;

  const pct = Math.max(0, Math.min(100, (secondsLeft / pauseSeconds) * 100));

  return (
    <div
      className="modal-overlay stage-transition-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="stage-transition-title"
    >
      <div className="modal-card panel stage-transition-card">
        <p className="stage-transition-eyebrow">Pipeline step-through</p>
        <h3 id="stage-transition-title">{stageTitle}</h3>
        <p className="hint stage-transition-copy">
          Proceed to run this step, or skip it. Auto-continues in{" "}
          <strong>{secondsLeft}s</strong> if you do nothing.
        </p>
        <div
          className="stage-transition-timer"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={pauseSeconds}
          aria-valuenow={secondsLeft}
        >
          <div className="stage-transition-timer-fill" style={{ width: `${pct}%` }} />
          <span className="stage-transition-timer-label">{secondsLeft}</span>
        </div>
        <div className="modal-actions stage-transition-actions">
          <button
            type="button"
            className="btn ghost"
            data-testid="stage-transition-skip"
            disabled={submitting}
            onClick={() => void submit("skip")}
          >
            Skip step
          </button>
          <button
            type="button"
            className="btn primary"
            data-testid="stage-transition-proceed"
            disabled={submitting}
            onClick={() => void submit("proceed")}
          >
            {submitting ? "Starting…" : "Proceed now"}
          </button>
        </div>
      </div>
    </div>
  );
}
