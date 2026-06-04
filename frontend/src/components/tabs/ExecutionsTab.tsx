import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";

export function ExecutionsTab() {
  const { runs, runId, refreshHome, openRun } = useApp();

  return (
    <main className="view tab-view">
      <section className="panel hero">
        <h2>Previous executions</h2>
        <p className="lead">
          Resume any run without stopping the active session. Switch to Pipeline to
          continue the current execution.
        </p>
      </section>
      <section className="panel">
        <div className="panel-head">
          <h3>Executions</h3>
          <button type="button" className="btn ghost sm" onClick={() => void refreshHome()}>
            Refresh
          </button>
        </div>
        <div className="runs-list">
          {!runs.length ? (
            <p className="empty-state">No executions yet. Start one from the Start tab.</p>
          ) : (
            runs.map((r) => {
              const prog = r.progress
                ? `${r.progress.done}/${r.progress.total} stages`
                : "";
              const pct =
                r.progress && r.progress.total > 0
                  ? Math.round((100 * r.progress.done) / r.progress.total)
                  : 0;
              const lastLog = r.last_log?.message
                ? escapeHtml(r.last_log.message).slice(0, 120)
                : "";
              const isActive = r.run_id === runId;
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
                    </div>
                    <div className="asset-meta">{r.input_audio_path || ""}</div>
                    <div className="asset-meta">
                      {prog} ({pct}%)
                      {r.selected_flow ? ` · ${r.selected_flow}` : ""}
                    </div>
                    {lastLog ? (
                      <div className="asset-meta muted">Last: {lastLog}</div>
                    ) : null}
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
