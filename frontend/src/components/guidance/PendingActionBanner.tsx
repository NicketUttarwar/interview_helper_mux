import { useApp } from "../../context/AppContext";
import { resolvePendingAction } from "../../utils/pendingAction";
import { pendingActionToSubstep } from "../../utils/stageSubsteps";
import { ReviewPanelControls } from "./ReviewPanelControls";

interface Props {
  compact?: boolean;
  stageId?: string;
}

export function PendingActionBanner({ compact, stageId }: Props) {
  const {
    run,
    apiGrants,
    closeActionModal,
    actionModalOpen,
    approveWriteAndContinue,
    actionBusy,
    activateSubstep,
  } = useApp();

  const pending = resolvePendingAction(run, apiGrants);
  if (!pending) return null;
  if (stageId && pending.stageId !== stageId) return null;

  const onPrimary = () => {
    if (pending.kind === "write_approval") {
      void approveWriteAndContinue(pending.stageId);
      return;
    }
    activateSubstep(pendingActionToSubstep(pending));
  };

  const onReviewFiles = () => {
    activateSubstep(pendingActionToSubstep(pending), { openModal: true });
  };

  const onReviewInline = () => {
    activateSubstep(pendingActionToSubstep(pending), { openModal: false });
    requestAnimationFrame(() => {
      document.getElementById("write-approval-panel")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  };

  const showInlineReview =
    pending.kind === "write_approval" && !actionModalOpen && Boolean(stageId);

  const handoffMessage =
    pending.kind === "handoff" && pending.handoffPaths?.length
      ? `Skim: ${pending.handoffPaths
          .slice(0, 2)
          .map((p) => p.split("/").pop())
          .join(", ")}${pending.handoffPaths.length > 2 ? "…" : ""}`
      : pending.message;

  return (
    <div
      className={`pending-action-banner kind-${pending.kind}${compact ? " compact" : ""} attention-required`}
      role="alert"
      data-testid="pending-action-banner"
    >
      <div className="pending-action-icon" aria-hidden>
        {pending.kind === "write_approval" ? "📋" : pending.kind === "handoff" ? "✓" : "!"}
      </div>
      <div className="pending-action-copy">
        <p className="pending-action-title">
          {pending.stageTitle} — {pending.title}
        </p>
        <p className="pending-action-message">{handoffMessage}</p>
        {!compact && pending.kind === "write_approval" ? (
          <p className="hint sm pending-action-hint">
            Staged files are ready on disk — click <strong>Save &amp; continue</strong> to
            approve and advance, or review first.
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
              disabled={actionBusy}
              onClick={onPrimary}
            >
              {pending.primaryLabel}
            </button>
            {pending.kind === "write_approval" && !actionModalOpen ? (
              <button
                type="button"
                className="btn ghost sm"
                data-testid="pending-action-review-files"
                disabled={actionBusy}
                onClick={onReviewFiles}
              >
                Review files first
              </button>
            ) : null}
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
