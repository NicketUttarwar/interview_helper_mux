import { useApp } from "../context/AppContext";

export function Toast() {
  const { toast, jobRunning, actionBusy } = useApp();
  if (!toast) return null;
  const extended = jobRunning || actionBusy;
  return (
    <div
      className={`toast level-${toast.level}${extended ? " toast-extended" : ""}`}
      role="status"
      aria-live={toast.level === "error" ? "assertive" : "polite"}
    >
      {toast.message}
    </div>
  );
}
