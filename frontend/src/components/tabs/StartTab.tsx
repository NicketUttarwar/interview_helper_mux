import { useApp } from "../../context/AppContext";
import { useLiveStatus } from "../../hooks/useLiveStatus";
import { formatBytes } from "../../utils";
import { InfoTooltip } from "../InfoTooltip";
import { StartPhaseGuidance } from "../guidance/PhaseGuidanceBanner";
import { ActionMarker } from "../guidance/ActionMarker";

export function StartTab() {
  const {
    assets,
    selectedAsset,
    setSelectedAsset,
    refreshHome,
    startRun,
    run,
    runId,
    setActiveTab,
    sessionLoadError,
    retryOpenRun,
    clearSession,
    openRunLoading,
    sessionReady,
    homeRefreshing,
    showToast,
    jobRunning,
    selectedStageId,
    logEntries,
    apiGrants,
    executeJob,
    runNextStage,
    openActionModal,
    setPipelineSubTab,
    selectStage,
    setActiveSubstepId,
    actionBusy,
  } = useApp();
  const sessionLocked = Boolean(runId);

  const live = useLiveStatus(run, {
    jobRunning,
    actionBusy,
    selectedStageId,
    logEntries,
    apiGrants,
    onExecute: (body) => void executeJob(body),
    onRunNext: () => void runNextStage(),
    onOpenCheckpoint: (stageId, substepId) => {
      if (stageId) void selectStage(stageId);
      if (substepId) setActiveSubstepId(substepId);
      openActionModal();
    },
    onGoLogs: () => setActiveTab("logs"),
    onGoStart: () => setActiveTab("start"),
    onGoPipeline: () => {
      setActiveTab("pipeline");
      setPipelineSubTab("stage");
    },
  });

  if (runId && !run) {
    return (
      <main className="view tab-view">
        <section className="panel hero hero-compact">
          <h2>Session recovery</h2>
          <p className="hint">
            The active execution could not be loaded. Retry or clear the session to start over.
          </p>
          {sessionLoadError ? (
            <p className="hint" role="alert">
              {sessionLoadError}
            </p>
          ) : null}
          <div className="flow-choice">
            <button
              type="button"
              className="btn primary"
              disabled={!sessionReady || openRunLoading}
              onClick={() => void retryOpenRun()}
            >
              {openRunLoading ? "Loading…" : "Retry load"}
            </button>
            <button
              type="button"
              className="btn danger ghost"
              disabled={!sessionReady}
              onClick={() => void clearSession()}
            >
              Clear session
            </button>
          </div>
        </section>
      </main>
    );
  }

  if (sessionLocked && run) {
    const sourcePath = run.meta?.input_audio_path || "Unknown source";
    const sourceName = sourcePath.split("/").pop() || sourcePath;
    return (
      <main className="view tab-view">
        <section className="panel hero hero-compact">
          <h2>Session in progress</h2>
          <p className="hint">
            Source audio is locked for this session. Continue in Pipeline — use{" "}
            <strong>Menu → Clear session</strong> only when you want to start over.
          </p>
          <p className="hint start-live-subline">
            <strong>{live.headline}</strong>
            {live.subline ? <> — {live.subline}</> : null}
          </p>
          {run.journey?.source_readiness?.band ? (
            <p className="hint" data-testid="source-readiness-banner">
              Source readiness:{" "}
              <strong className={`readiness-band readiness-band--${run.journey.source_readiness.band}`}>
                {run.journey.source_readiness.band}
              </strong>
              {typeof run.journey.source_readiness.score === "number"
                ? ` (${run.journey.source_readiness.score.toFixed(2)})`
                : ""}
              {(run.journey.source_readiness.reasons || []).length
                ? ` — ${(run.journey.source_readiness.reasons || []).slice(0, 2).join("; ")}`
                : ""}
            </p>
          ) : null}
        </section>
        <section className="panel panel-compact source-locked-panel">
          <h3>
            Locked source audio
            <InfoTooltip text="The interview file cannot be changed mid-session. This keeps the pipeline sequential and consistent." />
          </h3>
          <div className="source-locked-card">
            <div>
              <strong>{sourceName}</strong>
              <div className="asset-meta muted">{sourcePath}</div>
              {run.meta?.execution_number ? (
                <div className="asset-meta">
                  Execution #{run.meta.execution_number} · {run.run_id}
                </div>
              ) : null}
            </div>
            <span className="stage-status-pill done">Locked</span>
          </div>
          <div className="flow-choice">
            <button type="button" className="btn primary" onClick={() => setActiveTab("pipeline")}>
              Continue in Pipeline
            </button>
            <button type="button" className="btn ghost" onClick={() => setActiveTab("logs")}>
              View logs
            </button>
            <button
              type="button"
              className="btn danger ghost"
              disabled={!sessionReady}
              onClick={() => void clearSession()}
            >
              Clear session &amp; pick new audio
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="view tab-view start-tab-view">
      <section className="panel hero hero-compact">
        <h2>
          New execution
          <InfoTooltip text="Pick one interview file — it locks for the session once you start." />
        </h2>
      </section>
      <StartPhaseGuidance />
      <section
        className="panel panel-compact"
        data-testid="start-tab-ready"
        data-ready={sessionReady ? "true" : "false"}
      >
        <div className="panel-head">
          <h3>Source audio</h3>
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
        <div className="asset-list">
          {!assets.length ? (
            <p className="empty-state">No audio in ASSETS/. Add .wav files and refresh.</p>
          ) : (
            assets.map((f) => (
              <div
                key={f.path}
                className={`asset-item${selectedAsset === f.path ? " selected" : ""}`}
                data-testid={`start-asset-${f.name}`}
                onClick={() => setSelectedAsset(f.path)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setSelectedAsset(f.path);
                }}
                role="button"
                tabIndex={0}
              >
                <div className="asset-item-body">
                  <strong title={f.name}>{f.name}</strong>
                  <div className="asset-meta">{formatBytes(f.size_bytes)}</div>
                </div>
                <button
                  type="button"
                  className="btn primary sm btn-start"
                  data-testid={`start-execution-${f.name}`}
                  disabled={!sessionReady || openRunLoading}
                  onClick={(e) => {
                    e.stopPropagation();
                    void startRun(f.path);
                  }}
                >
                  <ActionMarker status="todo" /> Start
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
