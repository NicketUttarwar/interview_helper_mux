import { useState } from "react";
import { useApp } from "../../context/AppContext";
import { useLiveStatus } from "../../hooks/useLiveStatus";
import { formatBytes } from "../../utils";
import { InfoTooltip } from "../InfoTooltip";
import { StartPhaseGuidance } from "../guidance/PhaseGuidanceBanner";
import { PreviousSessionReusePanel } from "../guidance/PreviousSessionReusePanel";
import { ActionMarker } from "../guidance/ActionMarker";

type FlowIntent = "flow1" | "flow2" | "flow3";

const INTENT_CARDS: { id: FlowIntent; title: string; tooltip: string }[] = [
  {
    id: "flow1",
    title: "Full podcast",
    tooltip: "Complete episode with VO bridges, sound design, and mastered WAV.",
  },
  {
    id: "flow2",
    title: "Highlights",
    tooltip: "Up to five clips with montage SFX (~60s–3min mastered WAV).",
  },
  {
    id: "flow3",
    title: "Description",
    tooltip: "Third-person show blurb for directories — no audio output.",
  },
];

export function StartTab() {
  const {
    assets,
    selectedAsset,
    setSelectedAsset,
    refreshHome,
    startRun,
    config,
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
    acknowledgeHandoff,
    setPipelineSubTab,
    selectStage,
    setActiveSubstepId,
    actionBusy,
  } = useApp();
  const [flowIntent, setFlowIntent] = useState<FlowIntent>("flow1");
  const intentEnabled = config?.journey_ui?.intent_at_start !== false;
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
    onAcknowledgeHandoff: () => void acknowledgeHandoff(),
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
      {runId ? <PreviousSessionReusePanel /> : null}
      {intentEnabled ? (
        <section className="panel panel-compact">
          <h3>
            Output type
            <InfoTooltip text="You can change this later at Record & choose (G2)." />
          </h3>
          <div className="flow-intent-cards">
            {INTENT_CARDS.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`flow-intent-card${flowIntent === c.id ? " selected" : ""}`}
                data-testid={`flow-intent-${c.id}`}
                title={c.tooltip}
                onClick={() => setFlowIntent(c.id)}
              >
                <strong>{c.title}</strong>
                <InfoTooltip text={c.tooltip} label={`About ${c.title}`} />
              </button>
            ))}
          </div>
        </section>
      ) : null}
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
                    void startRun(f.path, intentEnabled ? flowIntent : undefined);
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
