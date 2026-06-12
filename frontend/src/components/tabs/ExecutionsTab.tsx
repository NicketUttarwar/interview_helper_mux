import { useState, type MouseEvent } from "react";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import { SourceAudioHashBadge } from "../guidance/SourceAudioHashBadge";
import { sourceHashShort } from "../../utils/sourceAudioHash";
import { isJobActivelyRunning } from "../../utils/jobStatus";

function jobStatusLabel(status?: string): string | null {
  if (!status || status === "idle" || status === "complete") return null;
  if (status === "running" || status === "running_with_warnings") return "Running";
  if (status === "error") return "Failed";
  if (status === "interrupted") return "Interrupted";
  if (status === "gate" || status === "needs_operator") return "Paused";
  return status.replace(/_/g, " ");
}

export function ExecutionsTab() {
  const {
    runs,
    runId,
    run,
    refreshHome,
    openRun,
    showToast,
    sessionReady,
    openRunLoading,
    homeRefreshing,
    setActiveTab,
  } = useApp();
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);
  const sessionLocked = Boolean(runId);
  const activeHash = sourceHashShort(run?.meta);
  const activeJobStatus = run?.job?.status;

  const tryOpenRun = (id: string) => {
    if (!sessionReady || openRunLoading) return;
    if (sessionLocked && id !== runId) {
      showToast("Clear session (Menu) before opening a different execution.");
      return;
    }
    setLoadingRunId(id);
    return openRun(id).finally(() => setLoadingRunId(null));
  };

  const openLogsForRun = (id: string, e: MouseEvent) => {
    e.stopPropagation();
    if (sessionLocked && id !== runId) {
      showToast("Clear session (Menu) before opening a different execution.");
      return;
    }
    void (async () => {
      if (id !== runId) await tryOpenRun(id);
      setActiveTab("logs");
    })();
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
          <button
            type="button"
            className="btn ghost sm"
            disabled={homeRefreshing}
            onClick={() => {
              void refreshHome().catch((e) => {
                showToast(e instanceof Error ? e.message : "Refresh failed");
              });
            }}
          >
            {homeRefreshing ? "Refreshing…" : "Refresh"}
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
              const done = r.progress?.done ?? 0;
              const total = r.progress?.total ?? 0;
              const prog = total ? `${done}/${total}` : "";
              const pct = total ? Math.round((done / total) * 100) : 0;
              const isActive = r.run_id === runId;
              const isDisabled =
                !sessionReady || openRunLoading || (sessionLocked && !isActive);
              const isLoading = loadingRunId === r.run_id;
              const lastLog = r.last_log?.message
                ? escapeHtml(r.last_log.message).slice(0, 80)
                : "";
              const runHash = sourceHashShort(r);
              const hashMatchesActive =
                Boolean(activeHash && runHash && activeHash === runHash);
              const jobStatus = isActive
                ? activeJobStatus
                : r.job_status;
              const statusLabel = jobStatusLabel(jobStatus);
              const showLock = sessionLocked && !isActive;
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
                      {showLock ? (
                        <span className="run-lock-pill" title="Session locked to another run">
                          🔒
                        </span>
                      ) : null}
                      {statusLabel ? (
                        <span
                          className={`run-job-pill status-${jobStatus}${isJobActivelyRunning({ status: jobStatus }) ? " running" : ""}`}
                        >
                          {statusLabel}
                        </span>
                      ) : null}
                      {hashMatchesActive ? (
                        <span className="run-same-audio-pill">Same audio</span>
                      ) : null}
                    </div>
                    <div className="asset-meta">
                      {formatTs(r.updated_at || r.created_at)}
                      {prog ? ` · ${prog} stages` : ""}
                      {r.selected_flow ? ` · ${r.selected_flow}` : ""}
                    </div>
                    {total > 0 ? (
                      <div
                        className="run-progress-bar"
                        role="progressbar"
                        aria-valuenow={pct}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`${pct}% stages complete`}
                      >
                        <span className="run-progress-fill" style={{ width: `${pct}%` }} />
                      </div>
                    ) : null}
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
                    {lastLog ? (
                      <button
                        type="button"
                        className="asset-meta muted run-last-log"
                        onClick={(e) => openLogsForRun(r.run_id, e)}
                        title="Open Logs tab"
                      >
                        {lastLog}
                      </button>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="btn primary sm"
                    disabled={isDisabled || isLoading}
                    onClick={(e) => {
                      e.stopPropagation();
                      tryOpenRun(r.run_id);
                    }}
                  >
                    {isLoading ? "Loading…" : isActive ? "Open" : "Resume"}
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
