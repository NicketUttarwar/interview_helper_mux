import { useMemo, useState, type MouseEvent } from "react";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import { PHASE_LABELS } from "../../constants/phases";
import { SourceAudioHashBadge } from "../guidance/SourceAudioHashBadge";
import { sourceHashShort } from "../../utils/sourceAudioHash";
import { resolveOperatorAction } from "../../utils/resolveOperatorAction";
import { isJobActivelyRunning } from "../../utils/jobStatus";
import type { RunSummary } from "../../types";

function jobStatusLabel(status?: string): string | null {
  if (!status || status === "idle" || status === "complete") return null;
  if (status === "running" || status === "running_with_warnings") return "Running";
  if (status === "error") return "Failed";
  if (status === "interrupted") return "Interrupted";
  if (status === "gate" || status === "needs_operator") return "Paused";
  return status.replace(/_/g, " ");
}

function RunRow({
  r,
  isActive,
  isImmediatePrevious,
  isDisabled,
  isLoading,
  activeHash,
  activeJobStatus,
  sessionLocked,
  tryOpenRun,
  openLogsForRun,
}: {
  r: RunSummary;
  isActive: boolean;
  isImmediatePrevious: boolean;
  isDisabled: boolean;
  isLoading: boolean;
  activeHash: string | null | undefined;
  activeJobStatus?: string;
  sessionLocked: boolean;
  tryOpenRun: (id: string) => void;
  openLogsForRun: (id: string, e: MouseEvent) => void;
}) {
  const done = r.progress?.done ?? 0;
  const total = r.progress?.total ?? 0;
  const prog = total ? `${done}/${total}` : "";
  const pct = total ? Math.round((done / total) * 100) : 0;
  const lastLog = r.last_log?.message ? escapeHtml(r.last_log.message).slice(0, 80) : "";
  const runHash = sourceHashShort(r);
  const hashMatchesActive = Boolean(activeHash && runHash && activeHash === runHash);
  const jobStatus = isActive ? activeJobStatus : r.job_status;
  const statusLabel = jobStatusLabel(jobStatus);
  const showLock = sessionLocked && !isActive;
  const attentionCount = r.attention_count ?? 0;
  const phaseLabel = r.operator_phase ? PHASE_LABELS[r.operator_phase] || r.operator_phase : null;
  const blockedHint =
    r.blocking_message || r.next_action
      ? String(r.blocking_message || r.next_action).slice(0, 80)
      : "";

  return (
    <div
      className={`run-item${isActive ? " run-item-active" : ""}${isImmediatePrevious ? " run-item-immediate-previous" : ""}${isDisabled ? " run-item-disabled" : ""}${hashMatchesActive ? " run-item-same-audio" : ""}`}
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
          : isImmediatePrevious
            ? "Immediate previous execution (reuse source)"
            : hashMatchesActive
              ? "Same source audio as active session"
              : undefined
      }
    >
      <div className="run-main">
        <div className="run-item-title-row">
          <strong>
            #{r.execution_number ?? "?"} · {r.run_id}
            {isActive ? " · active" : isImmediatePrevious ? " · previous" : ""}
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
          {hashMatchesActive ? <span className="run-same-audio-pill">Same audio</span> : null}
          {r.homunculus_version ? (
            <span className="run-same-audio-pill" data-testid="run-brain-pill">
              {r.homunculus_version === "0.1.0" ? "Homunculus 0.1.0" : `Brain ${r.homunculus_version}`}
            </span>
          ) : null}
          {attentionCount > 0 || jobStatus === "gate" ? (
            <span className="run-needs-you-pill">Needs you</span>
          ) : null}
        </div>
        {phaseLabel || blockedHint ? (
          <p className="hint sm run-item-blocked-hint">
            {phaseLabel ? `${phaseLabel}` : ""}
            {phaseLabel && blockedHint ? " · " : ""}
            {blockedHint}
          </p>
        ) : null}
        <div className="asset-meta">
          {formatTs(r.updated_at || r.created_at)}
          {prog ? ` · ${prog} stages` : ""}
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
    apiGrants,
    selectedStageId,
  } = useApp();
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);
  const [olderExpanded, setOlderExpanded] = useState(false);
  const sessionLocked = Boolean(runId);
  const activeHash = sourceHashShort(run?.meta);
  const activeJobStatus = run?.job?.status;
  const immediatePreviousId =
    run?.immediate_previous_run_id ??
    (run?.execution_number != null
      ? runs.find((r) => r.execution_number === (run.execution_number ?? 0) - 1)?.run_id
      : null);

  const { featured, older } = useMemo(() => {
    const featuredIds = new Set(
      [runId, immediatePreviousId].filter(Boolean) as string[],
    );
    const featuredRuns = runs.filter((r) => featuredIds.has(r.run_id));
    const olderRuns = runs.filter((r) => !featuredIds.has(r.run_id));
    featuredRuns.sort((a, b) => (b.execution_number ?? 0) - (a.execution_number ?? 0));
    olderRuns.sort((a, b) => (b.execution_number ?? 0) - (a.execution_number ?? 0));
    return { featured: featuredRuns, older: olderRuns };
  }, [runs, runId, immediatePreviousId]);

  const activeOperatorHeadline = run
    ? resolveOperatorAction(run, {
        selectedStageId,
        jobRunning: isJobActivelyRunning(run.job),
        apiGrants,
      }).headline
    : null;

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

  const renderRun = (r: RunSummary) => {
    const isActive = r.run_id === runId;
    const isImmediatePrevious = r.run_id === immediatePreviousId && !isActive;
    const isDisabled = !sessionReady || openRunLoading || (sessionLocked && !isActive);
    const isLoading = loadingRunId === r.run_id;
    return (
      <RunRow
        key={r.run_id}
        r={r}
        isActive={isActive}
        isImmediatePrevious={isImmediatePrevious}
        isDisabled={isDisabled}
        isLoading={isLoading}
        activeHash={activeHash}
        activeJobStatus={activeJobStatus}
        sessionLocked={sessionLocked}
        tryOpenRun={tryOpenRun}
        openLogsForRun={openLogsForRun}
      />
    );
  };

  return (
    <main className="view tab-view">
      <section className="panel panel-compact">
        <div className="panel-head">
          <div>
            <h2>Executions</h2>
            <p className="hint panel-head-sub">
              Current and immediate-previous runs are highlighted. Reuse copies outputs only from
              the previous execution when source audio matches.
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
            {activeOperatorHeadline ? (
              <p className="hint sm executions-active-substep">
                Operator focus: <strong>{activeOperatorHeadline}</strong>
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="runs-list">
          {!runs.length ? (
            <p className="empty-state">No runs yet.</p>
          ) : (
            <>
              {featured.length ? (
                <div className="runs-featured" data-testid="runs-featured">
                  {featured.map(renderRun)}
                </div>
              ) : null}
              {older.length ? (
                <details
                  className="runs-older-collapse"
                  open={olderExpanded}
                  onToggle={(e) => setOlderExpanded((e.target as HTMLDetailsElement).open)}
                >
                  <summary className="hint">
                    {older.length} older execution{older.length === 1 ? "" : "s"}
                  </summary>
                  <div className="runs-list-older">{older.map(renderRun)}</div>
                </details>
              ) : null}
            </>
          )}
        </div>
      </section>
    </main>
  );
}
