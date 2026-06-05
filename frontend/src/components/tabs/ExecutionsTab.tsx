import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";

export function ExecutionsTab() {
  const { runs, runId, refreshHome, openRun, showToast } = useApp();
  const sessionLocked = Boolean(runId);

  const tryOpenRun = (id: string) => {
    if (sessionLocked && id !== runId) {
      showToast("Clear session (Menu) before opening a different execution.");
      return;
    }
    void openRun(id);
  };

  return (
    <main className="view tab-view">
      <section className="panel panel-compact">
        <div className="panel-head">
          <h2>Previous runs</h2>
          <button type="button" className="btn ghost sm" onClick={() => void refreshHome()}>
            Refresh
          </button>
        </div>
        <div className="runs-list">
          {!runs.length ? (
            <p className="empty-state">No runs yet.</p>
          ) : (
            runs.map((r) => {
              const prog = r.progress
                ? `${r.progress.done}/${r.progress.total}`
                : "";
              const isActive = r.run_id === runId;
              const isDisabled = sessionLocked && !isActive;
              const lastLog = r.last_log?.message
                ? escapeHtml(r.last_log.message).slice(0, 80)
                : "";
              return (
                <div
                  key={r.run_id}
                  className={`run-item${isActive ? " run-item-active" : ""}${isDisabled ? " run-item-disabled" : ""}`}
                  onClick={() => tryOpenRun(r.run_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") tryOpenRun(r.run_id);
                  }}
                  role="button"
                  tabIndex={isDisabled ? -1 : 0}
                  aria-disabled={isDisabled}
                  title={
                    isDisabled
                      ? "Clear session to open a different execution"
                      : undefined
                  }
                >
                  <div className="run-main">
                    <strong>
                      #{r.execution_number ?? "?"} · {r.run_id}
                      {isActive ? " · active" : ""}
                    </strong>
                    <div className="asset-meta">
                      {formatTs(r.updated_at || r.created_at)}
                      {prog ? ` · ${prog} stages` : ""}
                      {r.selected_flow ? ` · ${r.selected_flow}` : ""}
                    </div>
                    {lastLog ? <div className="asset-meta muted">{lastLog}</div> : null}
                  </div>
                  <button
                    type="button"
                    className="btn primary sm"
                    disabled={isDisabled}
                    onClick={(e) => {
                      e.stopPropagation();
                      tryOpenRun(r.run_id);
                    }}
                  >
                    {isActive ? "Open" : "Resume"}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </section>
    </main>
  );
}
