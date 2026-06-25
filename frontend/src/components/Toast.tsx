import { useApp } from "../context/AppContext";

export function Toast() {
  const { toast, dismissToast, jobRunning, actionBusy } = useApp();
  if (!toast) return null;
  const extended = jobRunning || actionBusy;
  return (
    <div
      className={`toast level-${toast.level}${extended ? " toast-extended" : ""}`}
      role="status"
      aria-live={toast.level === "error" ? "assertive" : "polite"}
      onClick={() => dismissToast()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          dismissToast();
        }
      }}
      tabIndex={0}
      title="Click to dismiss"
    >
      {toast.message}
    </div>
  );
}
