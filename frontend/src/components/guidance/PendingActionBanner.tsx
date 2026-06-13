import { useApp } from "../../context/AppContext";
import { resolvePendingAction } from "../../utils/pendingAction";
import { ReviewPanelControls } from "./ReviewPanelControls";

interface Props {
  compact?: boolean;
  /** When set, only show if the pending action targets this stage. */
  stageId?: string;
}

export function PendingActionBanner({ compact, stageId }: Props) {
  const {
    run,
    apiGrants,
    openActionModal,
    closeActionModal,
    selectStage,
    acknowledgeHandoff,
    actionModalOpen,
    setActiveTab,
    setPipelineSubTab,
  } = useApp();

  const pending = resolvePendingAction(run, apiGrants);
  if (!pending) return null;
  if (stageId && pending.stageId !== stageId) return null;

  const onPrimary = () => {
    if (pending.stageId) void selectStage(pending.stageId);
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    if (pending.kind === "handoff") {
      void acknowledgeHandoff();
      return;
    }
    openActionModal();
  };

  const onReviewInline = () => {
    if (pending.stageId) void selectStage(pending.stageId);
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    closeActionModal();
    requestAnimationFrame(() => {
      document.getElementById("write-approval-panel")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  };

  const showInlineReview =
    pending.kind === "write_approval" && !actionModalOpen && Boolean(stageId);

  return (
    <div
      className={`pending-action-banner kind-${pending.kind}${compact ? " compact" : ""}`}
      role="alert"
      data-testid="pending-action-banner"
    >
      <div className="pending-action-icon" aria-hidden>
        {pending.kind === "write_approval" ? "📋" : pending.kind === "handoff" ? "✓" : "!"}
      </div>
      <div className="pending-action-copy">
        <p className="pending-action-title">{pending.title}</p>
        <p className="pending-action-message">{pending.message}</p>
        {!compact && pending.kind === "write_approval" ? (
          <p className="hint sm pending-action-hint">
            Listen to audio, preview JSON, then click <strong>Save &amp; continue</strong> to write
            files to disk and advance.
          </p>
        ) : null}
      </div>
      <div className="pending-action-buttons">
        {!actionModalOpen ? (
          <>
            <button
              type="button"
              className="btn primary sm"
              data-testid="pending-action-primary"
              onClick={onPrimary}
            >
              {pending.primaryLabel}
            </button>
            {showInlineReview ? (
              <button type="button" className="btn ghost sm" onClick={onReviewInline}>
                Review here
              </button>
            ) : null}
          </>
        ) : (
          <button type="button" className="btn ghost sm" onClick={closeActionModal}>
            Review inline instead
          </button>
        )}
        {!compact ? <ReviewPanelControls requirePending={false} /> : null}
      </div>
    </div>
  );
}
