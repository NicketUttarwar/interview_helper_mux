import { useApp } from "../../context/AppContext";

export function ConfirmDialog() {
  const { confirmMessage, resolveConfirm } = useApp();
  if (!confirmMessage) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card panel">
        <h3>Confirm</h3>
        <p className="lead">{confirmMessage}</p>
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={() => resolveConfirm(false)}>
            Cancel
          </button>
          <button type="button" className="btn primary" onClick={() => resolveConfirm(true)}>
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
