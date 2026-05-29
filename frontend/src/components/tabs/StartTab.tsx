import { useApp } from "../../context/AppContext";
import { formatBytes } from "../../utils";

export function StartTab() {
  const { assets, selectedAsset, setSelectedAsset, refreshHome, startRun } = useApp();

  return (
    <main className="view tab-view">
      <section className="panel hero">
        <h2>Source audio</h2>
        <p className="lead">
          Input files live under <code>ASSETS/</code>. Pick a file and start a new
          immutable execution folder (<code>exec_001_…</code>).
        </p>
      </section>
      <section className="panel">
        <div className="panel-head">
          <h3>Input audio</h3>
          <button type="button" className="btn ghost sm" onClick={() => void refreshHome()}>
            Refresh
          </button>
        </div>
        <div className="asset-list">
          {!assets.length ? (
            <p className="empty-state">
              No input audio in ASSETS/ (outside executions/). Add .wav files and refresh.
            </p>
          ) : (
            assets.map((f) => (
              <div
                key={f.path}
                className={`asset-item${selectedAsset === f.path ? " selected" : ""}`}
                onClick={() => setSelectedAsset(f.path)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setSelectedAsset(f.path);
                }}
                role="button"
                tabIndex={0}
              >
                <div>
                  <strong>{f.name}</strong>
                  <div className="asset-meta">
                    {f.path} · {formatBytes(f.size_bytes)}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn primary sm btn-start"
                  onClick={(e) => {
                    e.stopPropagation();
                    void startRun(f.path);
                  }}
                >
                  New execution
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
