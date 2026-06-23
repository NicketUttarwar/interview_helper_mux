import { useApp } from "../../context/AppContext";
import { useGlobalOperatorAction } from "../../hooks/useOperatorAction";
import { invokeOperatorActionPrimary, executeBodyForStage } from "../../utils/operatorActionHandlers";

interface Props {
  compact?: boolean;
  stageId?: string;
}

export function PendingActionBanner({ compact, stageId }: Props) {
  const {
    run,
    apiGrants,
    jobRunning,
    actionBusy,
    setActiveTab,
    selectStage,
    setActiveSubstepId,
    openActionModal,
    executeJob,
    runNextStage,
    setActivityLogTab,
    setActivityLogCollapsed,
  } = useApp();

  const action = useGlobalOperatorAction(run, {
    selectedStageId: stageId ?? null,
    jobRunning,
    apiGrants,
  });

  if (!run || action.mode !== "needs_you" || !action.stageId) return null;
  if (stageId && action.stageId !== stageId) return null;

  const stageTitle =
    run.stages.find((s) => s.id === action.stageId)?.title ?? action.stageId;

  const busy = jobRunning || actionBusy;

  const onPrimary = () => {
    if (busy) return;
    setActiveTab("pipeline");
    invokeOperatorActionPrimary(action, {
      openModal: (sid, subId) => {
        if (sid) void selectStage(sid);
        if (subId) setActiveSubstepId(subId);
        openActionModal();
      },
      runStage: (sid) => void executeJob(executeBodyForStage(sid)),
      continueNext: () => void runNextStage(),
      viewLogs: () => {
        setActivityLogTab("live");
        setActivityLogCollapsed(false);
      },
    });
  };

  return (
    <div
      className={`pending-action-banner kind-${action.blockingReason ?? "blocked"}${compact ? " compact" : ""} attention-required`}
      role="alert"
      data-testid="pending-action-banner"
    >
      <div className="pending-action-icon" aria-hidden>
        {action.blockingReason === "write_approval"
          ? "📋"
          : action.blockingReason === "handoff_review"
            ? "✓"
            : "!"}
      </div>
      <div className="pending-action-copy">
        <p className="pending-action-title">
          {stageTitle} — {action.headline}
        </p>
        {action.subline ? (
          <p className="pending-action-message">{action.subline}</p>
        ) : null}
        {!compact ? (
          <p className="hint sm pending-action-hint">
            Use <strong>StepActionHeader</strong> or the <strong>Steps</strong> sidebar in Pipeline.
          </p>
        ) : null}
      </div>
      <div className="pending-action-buttons">
        <button
          type="button"
          className="btn primary sm"
          data-testid="pending-action-primary"
          disabled={busy}
          onClick={onPrimary}
        >
          {busy ? (
            <>
              <span className="spinner-inline" aria-hidden /> Working…
            </>
          ) : (
            action.primaryLabel
          )}
        </button>
      </div>
    </div>
  );
}
