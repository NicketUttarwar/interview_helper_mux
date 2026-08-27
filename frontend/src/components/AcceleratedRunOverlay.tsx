import { useApp } from "../context/AppContext";
import { usePartialAutoGPublish } from "../hooks/usePartialAutoGPublish";
import { shouldShowAcceleratedRunOverlay } from "../utils/partialAcceleratedGuard";

export function AcceleratedRunOverlay() {
  const { run, jobRunning, setActiveTab } = useApp();
  const gPublish = usePartialAutoGPublish(run);
  const visible = shouldShowAcceleratedRunOverlay(run, gPublish, { jobRunning });

  if (!visible) return null;

  return (
    <div
      className="accelerated-run-overlay"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="accelerated-run-overlay-title"
      aria-live="polite"
      data-testid="accelerated-run-overlay"
    >
      <div className="accelerated-run-overlay-card">
        <p id="accelerated-run-overlay-title" className="accelerated-run-overlay-title">
          Accelerated run in progress
        </p>
        <p className="accelerated-run-overlay-message hint">
          You&apos;ll be prompted when your input is needed — transcript review and S3 upload
          are the only manual steps. Watch Pipeline and Logs for progress.
        </p>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => setActiveTab("logs")}
        >
          View logs
        </button>
      </div>
    </div>
  );
}
