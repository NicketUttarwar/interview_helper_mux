import { useApp } from "../context/AppContext";

export function SessionStaleOverlay() {
  const { sessionStale, takeOverSession } = useApp();

  if (!sessionStale) return null;

  return (
    <div className="session-stale-overlay" role="alertdialog" aria-labelledby="session-stale-title">
      <div className="session-stale-card">
        <h2 id="session-stale-title">Another tab is running this session</h2>
        <p>
          A newer browser tab is controlling this pipeline. This tab is read-only so runs and
          checkpoints are not changed from two places at once.
        </p>
        <div className="session-stale-actions">
          <button type="button" className="btn primary" onClick={() => void takeOverSession()}>
            Take over in this tab
          </button>
          <button
            type="button"
            className="btn secondary"
            onClick={() => window.location.reload()}
          >
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}
