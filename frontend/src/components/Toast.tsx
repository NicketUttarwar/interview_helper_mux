import { useApp } from "../context/AppContext";

export function Toast() {
  const { toast, jobRunning, actionBusy } = useApp();
  if (!toast) return null;
  const extended = jobRunning || actionBusy;
  return (
    <div className={`toast${extended ? " toast-extended" : ""}`} role="status">
      {toast}
    </div>
  );
}
