import { useMemo } from "react";
import { useApp } from "../../context/AppContext";
import { resolvePipelineNav } from "../../utils/pipelineNavigation";
import { firstTodoItem } from "../../utils/stageGuidance";
import { resolveStagePrimaryAction } from "../../utils/stagePrimaryAction";
import { resolvePrecleanOffer } from "../../utils/preclean";
import { PHASE_LABELS } from "../../constants/phases";
import { PendingActionBanner } from "../guidance/PendingActionBanner";
import { resolvePendingAction } from "../../utils/pendingAction";
import { primaryClickForPendingAction } from "../../utils/operatorNavigate";
import { PhaseGuidanceBanner } from "../guidance/PhaseGuidanceBanner";
import { AttentionQueuePanel } from "../guidance/AttentionQueuePanel";
import { PreviewListenPromo } from "../guidance/PreviewListenPromo";
import { QcSummaryCard } from "../gates/QcSummaryCard";
import { topAttentionItem } from "../../utils/attentionQueue";

export function PipelineCommandCenter() {
  const {
    run,
    selectedStageId,
    selectedStage,
    jobRunning,
    apiGrants,
    sessionReady,
    selectStage,
    openActionModal,
    setActiveTab,
    setPipelineSubTab,
    acknowledgeHandoff,
    executeJob,
    runNextStage,
    approveWriteAndContinue,
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

  const pendingAction = useMemo(
    () => (run ? resolvePendingAction(run, apiGrants) : null),
    [run, apiGrants],
  );

  const headerAction = useMemo(() => {
    if (!run) return null;
    const actionStage = selectedStage || nav.currentStage || nav.nextStage;
    if (!actionStage) return null;
    const offer = resolvePrecleanOffer(actionStage, run.meta);
    return resolveStagePrimaryAction(actionStage, run, nav, {
      jobRunning,
      hasPrecleanOffer: Boolean(offer),
    });
  }, [run, selectedStage, nav, jobRunning]);

  if (!run) return null;

  const phase = run.journey?.phase ?? run.meta?.operator_phase ?? "prepare";
  const phaseGoal =
    run.journey?.phase_guidance?.[phase]?.goal ||
    PHASE_LABELS[phase] ||
    "";

  const blocking = run.journey?.blocking ?? run.blocking;
  const blocked = Boolean(blocking?.blocked);
  const topAttention = topAttentionItem(run, apiGrants);

  const actionStage = selectedStage || nav.currentStage || nav.nextStage;
  const topTodo = actionStage?.guidance ? firstTodoItem(actionStage.guidance) : null;

  const onHeaderClick = () => {
    if (!headerAction || headerAction.disabled) return;
    if (pendingAction) {
      primaryClickForPendingAction(pendingAction, {
        selectStage: (id) => void selectStage(id),
        setActiveTab,
        setPipelineSubTab,
        openActionModal,
        closeActionModal: () => {},
        approveWrite: (id) => void approveWriteAndContinue(id),
      });
      return;
    }
    switch (headerAction.kind) {
      case "run":
        if (headerAction.targetStageId && headerAction.targetStageId !== actionStage?.id) {
          void selectStage(headerAction.targetStageId).then(() => {
            if (headerAction.runStageId === nav.nextStage?.id) void runNextStage();
            else if (headerAction.runStageId) {
              void executeJob({ mode: "stage", stage: headerAction.runStageId });
            }
          });
          return;
        }
        if (headerAction.runStageId === nav.nextStage?.id) void runNextStage();
        else if (headerAction.runStageId) {
          void executeJob({ mode: "stage", stage: headerAction.runStageId });
        } else void runNextStage();
        return;
      case "checkpoint":
        if (headerAction.targetStageId) void selectStage(headerAction.targetStageId);
        openActionModal();
        return;
      case "handoff":
        void acknowledgeHandoff();
        return;
      case "navigate":
        if (headerAction.targetStageId) void selectStage(headerAction.targetStageId);
        return;
      default:
        return;
    }
  };

  const showHeaderBtn =
    headerAction &&
    !pendingAction &&
    !jobRunning &&
    (headerAction.kind === "run" ||
      headerAction.kind === "checkpoint" ||
      headerAction.kind === "handoff" ||
      headerAction.kind === "navigate");

  const qcFailed = run.journey?.deliverable?.qc_passed === false;

  return (
    <section className="pipeline-command-center panel" aria-label="Pipeline progress">
      <PhaseGuidanceBanner run={run} compact />
      <AttentionQueuePanel hideWhenSingleWriteApproval />
      <PreviewListenPromo />
      {qcFailed ? (
        <div className="pipeline-qc-promo panel-inset">
          <QcSummaryCard qcKey="verify_master" stageId="master_flow1" />
        </div>
      ) : null}
      <PendingActionBanner />
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
              ? blocking?.message || topAttention?.title || "Action required"
              : nav.currentStage?.title || nav.nextStage?.title || "Pipeline"}
          </h2>
          {!blocked ? (
            <p className="pipeline-command-status">{nav.statusLine}</p>
          ) : topAttention ? (
            <p className="hint sm pipeline-command-status muted">
              Step {nav.currentNumber ?? "?"} — {topAttention.stageTitle}
            </p>
          ) : null}
          {!blocked && phaseGoal ? (
            <p className="hint sm pipeline-command-phase-goal">{phaseGoal}</p>
          ) : null}
          {topTodo && !showHeaderBtn && !blocked ? (
            <p className="hint pipeline-command-next">
              <span className="action-marker status-todo" aria-hidden>
                ●
              </span>{" "}
              {topTodo.label}
            </p>
          ) : nav.nextLine && !showHeaderBtn && !blocked ? (
            <p className="hint pipeline-command-next">{nav.nextLine}</p>
          ) : null}
        </div>
        {showHeaderBtn && headerAction ? (
          <div className="pipeline-command-actions">
            <button
              type="button"
              className="btn primary"
              disabled={headerAction.disabled || !sessionReady}
              data-testid="pipeline-command-primary"
              onClick={onHeaderClick}
            >
              {headerAction.label}
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
