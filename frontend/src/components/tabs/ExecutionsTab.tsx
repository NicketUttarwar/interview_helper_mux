import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import { SourceAudioHashBadge } from "../guidance/SourceAudioHashBadge";
import { sourceHashShort } from "../../utils/sourceAudioHash";

export function ExecutionsTab() {
  const { runs, runId, run, refreshHome, openRun, showToast } = useApp();
  const sessionLocked = Boolean(runId);
  const activeHash = sourceHashShort(run?.meta);

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
          <div>
            <h2>Previous runs</h2>
            <p className="hint panel-head-sub">
              Runs with the same audio hash used the same source WAV — reuse outputs per stage in
              Pipeline.
            </p>
          </div>
          <button type="button" className="btn ghost sm" onClick={() => void refreshHome()}>
            Refresh
          </button>
        </div>
        {activeHash ? (
          <div className="executions-active-hash panel-inset">
            <span className="muted">Active session hash</span>
            <SourceAudioHashBadge
              hashShort={activeHash}
              hashFull={run?.meta?.source_audio_hash}
              label=""
            />
          </div>
        ) : null}
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
              const runHash = sourceHashShort(r);
              const hashMatchesActive =
                Boolean(activeHash && runHash && activeHash === runHash);
              return (
                <div
                  key={r.run_id}
                  className={`run-item${isActive ? " run-item-active" : ""}${isDisabled ? " run-item-disabled" : ""}${hashMatchesActive ? " run-item-same-audio" : ""}`}
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
                      : hashMatchesActive
                        ? "Same source audio as active session"
                        : undefined
                  }
                >
                  <div className="run-main">
                    <div className="run-item-title-row">
                      <strong>
                        #{r.execution_number ?? "?"} · {r.run_id}
                        {isActive ? " · active" : ""}
                      </strong>
                      {hashMatchesActive ? (
                        <span className="run-same-audio-pill">Same audio</span>
                      ) : null}
                    </div>
                    <div className="asset-meta">
                      {formatTs(r.updated_at || r.created_at)}
                      {prog ? ` · ${prog} stages` : ""}
                      {r.selected_flow ? ` · ${r.selected_flow}` : ""}
                    </div>
                    {runHash ? (
                      <div className="run-item-hash-row">
                        <SourceAudioHashBadge
                          hashShort={runHash}
                          hashFull={r.source_audio_hash}
                          matched={hashMatchesActive}
                          label="Hash"
                        />
                      </div>
                    ) : null}
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
