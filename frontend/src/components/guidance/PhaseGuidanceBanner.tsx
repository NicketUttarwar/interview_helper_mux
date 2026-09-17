import { useState } from "react";
import type { OperatorPhase, RunData } from "../../types";
import { PHASE_LABELS, phaseLabel } from "../../constants/phases";
import { ActionMarker } from "./ActionMarker";
import { useApp } from "../../context/AppContext";
import { WORKFLOW_STEPS } from "../../utils/workflowSteps";
import { isPhaseFullyComplete } from "../../utils/phaseSubsteps";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";
import { firstTodoStepId } from "../../utils/resolveActiveStep";
import { api } from "../../api/client";

interface Props {
  run: RunData;
  compact?: boolean;
}

export function PhaseGuidanceBanner({ run, compact }: Props) {
  const { setActiveTab, selectStage, setActiveStepId, refreshRun, executeJob, showToast } = useApp();
  const phase = run.journey?.phase ?? "prepare";
  const phaseGuidance = run.journey?.phase_guidance?.[phase];
  const blocking = run.journey?.blocking ?? run.blocking;
  const escalations = run.resilience?.open_escalations || [];
  const thrash = run.thrash;
  const deliveryPin = run.delivery_pin;
  const wastedCounts = run.wasted_work?.counts || {};
  const [busy, setBusy] = useState<string | null>(null);
  const showUnstick = Boolean(thrash?.active || Boolean(run.meta?.needs_operator));
  const whyPinned =
    deliveryPin?.from_stage || thrash?.pin
      ? {
          stage: deliveryPin?.from_stage || thrash?.pin || "",
          intent: deliveryPin?.intent || thrash?.fail_class || "",
          reason: deliveryPin?.reason || "",
          source: deliveryPin?.source || (thrash?.active ? "thrash" : ""),
        }
      : null;

  const goal =
    phaseGuidance?.goal ||
    WORKFLOW_STEPS.find((s) => s.id === phase)?.tooltip ||
    "";

  const progress = phaseGuidance?.progress || run.journey?.phase_progress?.[phase];
  const actions = (phaseGuidance?.actions || []).slice(0, compact ? 2 : 3);
  const phaseComplete = isPhaseFullyComplete(run, phase);

  const goToStage = (stageId?: string) => {
    if (!stageId) return;
    setActiveTab("pipeline");
    void selectStage(stageId);
    const stepId = firstTodoStepId(run, stageId);
    if (stepId) setActiveStepId(stepId);
  };

  const resolveEscalation = async (stageId: string, optionId: string) => {
    setBusy(`${stageId}:${optionId}`);
    try {
      await api(`/api/runs/${run.run_id}/escalations/${stageId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ chosen_option: optionId }),
      });
      await refreshRun();
    } finally {
      setBusy(null);
    }
  };

  const unstickDelivery = async (andResume: boolean) => {
    setBusy(andResume ? "unstick-resume" : "unstick");
    try {
      const out = await api<{
        ok?: boolean;
        from_stage?: string;
        mode?: string;
        thrash_cleared?: boolean;
        phase_a_sealed?: boolean;
        job?: unknown;
      }>(`/api/runs/${run.run_id}/delivery/unstick`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clear_needs_operator: true,
          execute_resume: andResume,
        }),
      });
      await refreshRun();
      const pin = out.from_stage || thrash?.pin;
      if (pin) goToStage(pin);
      if (andResume && out.from_stage && !out.job) {
        await executeJob({
          mode: (out.mode as "delivery" | "analysis") || "delivery",
          from_stage: out.from_stage,
        });
      } else if (andResume && out.job) {
        showToast(`Resumed delivery from ${out.from_stage || "pin"}`, "success");
      } else {
        showToast(
          `Unstick ready${out.from_stage ? ` → ${out.from_stage}` : ""}`,
          "success",
        );
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Unstick failed", "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className={`phase-guidance-banner panel-inset${phaseComplete ? " phase-complete" : ""}`} aria-label="Phase guidance">
      {phaseComplete ? <StepDoneBanner variant="phase" title={`${PHASE_LABELS[phase] || phase} phase complete`} /> : null}
      <div className="phase-guidance-head">
        <h3 className="phase-guidance-title">
          {PHASE_LABELS[phase] || phase} phase
          {progress && progress.total > 0 ? (
            <span className="phase-guidance-progress muted">
              · {progress.done}/{progress.total} steps done
            </span>
          ) : null}
        </h3>
      </div>
      {goal ? <p className="hint phase-guidance-goal">{goal}</p> : null}
      {whyPinned ? (
        <p className="hint phase-guidance-why-pin" role="status">
          Why pinned: <code>{whyPinned.stage}</code>
          {whyPinned.intent ? (
            <>
              {" "}
              · intent <code>{whyPinned.intent}</code>
            </>
          ) : null}
          {whyPinned.reason ? <> · {whyPinned.reason}</> : null}
          {whyPinned.source ? <span className="muted"> ({whyPinned.source})</span> : null}
          {whyPinned.stage ? (
            <>
              {" "}
              <button type="button" className="btn ghost sm" onClick={() => goToStage(whyPinned.stage)}>
                Open pin
              </button>
            </>
          ) : null}
        </p>
      ) : null}
      {thrash?.active ? (
        <div className="phase-guidance-thrash" role="status">
          <p className="hint">
            Delivery thrash detected: class <code>{thrash.fail_class}</code>
            {thrash.pin ? <> · pin <code>{thrash.pin}</code></> : null}
            {typeof thrash.hit_count === "number" ? <> · {thrash.hit_count} hits</> : null}
          </p>
          {thrash.pin ? (
            <button type="button" className="btn sm" onClick={() => goToStage(thrash.pin)}>
              Open pin stage
            </button>
          ) : null}
          <button
            type="button"
            className="btn sm"
            disabled={busy === "unstick" || busy === "unstick-resume"}
            onClick={() => void unstickDelivery(false)}
          >
            Unstick delivery
          </button>
          <button
            type="button"
            className="btn sm"
            disabled={busy === "unstick" || busy === "unstick-resume"}
            onClick={() => void unstickDelivery(true)}
          >
            Unstick + resume
          </button>
        </div>
      ) : null}
      {showUnstick && !thrash?.active ? (
        <div className="phase-guidance-thrash" role="status">
          <p className="hint">Delivery needs operator — promote orphans, seal Phase A, clear thrash, pin resume.</p>
          <button
            type="button"
            className="btn sm"
            disabled={busy === "unstick" || busy === "unstick-resume"}
            onClick={() => void unstickDelivery(false)}
          >
            Unstick delivery
          </button>
          <button
            type="button"
            className="btn sm"
            disabled={busy === "unstick" || busy === "unstick-resume"}
            onClick={() => void unstickDelivery(true)}
          >
            Unstick + resume
          </button>
        </div>
      ) : null}
      {Object.keys(wastedCounts).length > 0 && !compact ? (
        <p className="hint muted" aria-label="Wasted work summary">
          Heal signals:{" "}
          {Object.entries(wastedCounts)
            .slice(0, 5)
            .map(([k, v]) => `${k}×${v}`)
            .join(" · ")}
        </p>
      ) : null}
      {escalations.length > 0 ? (
        <ul className="stage-guidance-list phase-guidance-actions" aria-label="Open escalations">
          {escalations.slice(0, compact ? 1 : 3).map((esc) => (
            <li key={esc.stage_id} className="stage-guidance-item status-todo">
              <ActionMarker status="todo" />
              <span className="stage-guidance-label">
                Escalation ({esc.stage_id}): {esc.failed_invariant}
              </span>
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => goToStage(esc.resume_stage || esc.stage_id)}
              >
                Go to step
              </button>
              {(esc.options || []).slice(0, 2).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="btn sm"
                  disabled={busy === `${esc.stage_id}:${opt.id}`}
                  onClick={() => void resolveEscalation(esc.stage_id, opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </li>
          ))}
        </ul>
      ) : null}
      {blocking?.blocked && blocking.message ? (
        <ul className="stage-guidance-list phase-guidance-actions">
          <li className="stage-guidance-item status-todo">
            <ActionMarker status="todo" />
            <span className="stage-guidance-label">{blocking.message}</span>
            {blocking.stage_id ? (
              <button type="button" className="btn ghost sm" onClick={() => goToStage(blocking.stage_id || undefined)}>
                Go to step
              </button>
            ) : null}
          </li>
        </ul>
      ) : null}
      {actions.length > 0 ? (
        <ul className="stage-guidance-list phase-guidance-actions">
          {actions.map((item) => (
            <li
              key={`${item.from_stage_id || ""}-${item.id}`}
              className={`stage-guidance-item status-${item.status}`}
            >
              <ActionMarker status={item.status} />
              <span className="stage-guidance-label">
                {item.from_stage_title ? `${item.from_stage_title}: ` : ""}
                {item.label}
              </span>
              {item.stage_id || item.from_stage_id ? (
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => goToStage(item.stage_id || item.from_stage_id)}
                >
                  Go to step
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {compact && (phaseGuidance?.actions?.length || 0) > 2 ? (
        <p className="hint sm">More steps listed in the pipeline step list.</p>
      ) : null}
    </section>
  );
}

export function StartPhaseGuidance() {
  return (
    <section className="phase-guidance-banner panel-inset" aria-label="Start guidance">
      <h3 className="phase-guidance-title">Start</h3>
      <p className="hint phase-guidance-goal">
        Pick run mode, brain, destination podcast, then one interview WAV from ASSETS/.
      </p>
      <ol className="hint sm start-phase-steps">
            <li>Choose Manual, Partially accelerated (default), or Full-auto; then Brain (default 0.2.0)</li>
            <li>Select the destination podcast (default Zero Shot)</li>
            <li>Click Start on your chosen file</li>
      </ol>
    </section>
  );
}

export function phaseLabelForOperatorPhase(phase: OperatorPhase | "start"): string {
  return phaseLabel(phase);
}
