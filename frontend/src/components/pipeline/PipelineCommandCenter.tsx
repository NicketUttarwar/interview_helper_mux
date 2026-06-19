import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { PHASE_LABELS } from "../../constants/phases";
import { PhaseGuidanceBanner } from "../guidance/PhaseGuidanceBanner";
import { PreviewListenPromo } from "../guidance/PreviewListenPromo";
import { QcSummaryCard } from "../gates/QcSummaryCard";
import { useStageProgress } from "../../hooks/useStageProgress";

export function PipelineCommandCenter() {
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
  const phaseGoal =
    run.journey?.phase_guidance?.[phase]?.goal ||
    PHASE_LABELS[phase] ||
    "";

  const blocking = run.journey?.blocking ?? run.blocking;
  const blocked = Boolean(blocking?.blocked);
  const qcFailed = run.journey?.deliverable?.qc_passed === false;

  const scrollToFocusStep = () => {
    const sid = nav.focusStageId;
    if (!sid) return;
    document
      .querySelector(`[data-testid="pipeline-step-${sid}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <section className="pipeline-command-center panel" aria-label="Pipeline progress">
      <PhaseGuidanceBanner run={run} compact />
      <PreviewListenPromo />
      {qcFailed ? (
        <div className="pipeline-qc-promo panel-inset">
          <QcSummaryCard qcKey="verify_master" stageId="master_flow1" />
        </div>
      ) : null}
      <div className="pipeline-command-head">
        <div>
          {!blocked ? (
            <p
              className="pipeline-command-eyebrow"
              title="Individual automated or manual stage within the current workflow phase."
            >
              {nav.currentNumber
                ? `Pipeline step ${nav.currentNumber} of ${nav.numberedStages.length}${
                    nav.currentStage?.guidance?.phase_label
                      ? ` · ${nav.currentStage.guidance.phase_label} phase`
                      : ""
                  }`
                : `Pipeline · ${nav.numberedStages.length} steps`}
            </p>
          ) : null}
          <h2 className="pipeline-command-title">
            {blocked
              ? blocking?.message || "Action required"
              : nav.currentStage?.title || nav.nextStage?.title || "Pipeline"}
          </h2>
          {!blocked ? (
            <p className="pipeline-command-status">{nav.statusLine}</p>
          ) : (
            <p className="hint sm pipeline-command-status">
              <button type="button" className="btn link sm" onClick={scrollToFocusStep}>
                See step in sidebar
              </button>
            </p>
          )}
          {!blocked && phaseGoal ? (
            <p className="hint sm pipeline-command-phase-goal">{phaseGoal}</p>
          ) : null}
          {activeSubstepGlobal && !blocked ? (
            <p className="hint sm pipeline-command-substep">
              Current action in sidebar: <strong>{activeSubstepGlobal.label}</strong>
            </p>
          ) : null}
          {!blocked && nav.nextStage ? (
            <p className="hint pipeline-command-next">
              Next: <strong>{nav.nextStage.title}</strong>
              {nav.nextLine ? ` — ${nav.nextLine}` : ""}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
