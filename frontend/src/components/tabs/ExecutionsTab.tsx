import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";

export function ExecutionsTab() {
  const { runs, runId, refreshHome, openRun } = useApp();

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
              const lastLog = r.last_log?.message
                ? escapeHtml(r.last_log.message).slice(0, 80)
                : "";
              return (
                <div
                  key={r.run_id}
                  className={`run-item${isActive ? " run-item-active" : ""}`}
                  onClick={() => void openRun(r.run_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void openRun(r.run_id);
                  }}
                  role="button"
                  tabIndex={0}
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
                    onClick={(e) => {
                      e.stopPropagation();
                      void openRun(r.run_id);
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
