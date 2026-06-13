import { useApp } from "../../context/AppContext";
import { resolvePendingAction } from "../../utils/pendingAction";

interface Props {
  /** When false, hide when no pending action (default true). */
  requirePending?: boolean;
}

export function ReviewPanelControls({ requirePending = true }: Props) {
  const { run, apiGrants, actionModalOpen, openActionModal, closeActionModal } = useApp();
  const pending = resolvePendingAction(run, apiGrants);

  if (requirePending && !pending) return null;

  if (actionModalOpen) {
    return (
      <div className="review-panel-controls">
        <span className="review-panel-status muted">Full-screen review open</span>
        <button type="button" className="btn ghost sm" onClick={closeActionModal}>
          Continue inline
        </button>
      </div>
    );
  }

  return (
    <div className="review-panel-controls">
      <button
        type="button"
        className="btn ghost sm"
        data-testid="open-fullscreen-review"
        onClick={openActionModal}
      >
        Open full-screen review
      </button>
    </div>
  );
}
