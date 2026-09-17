import { useApp } from "../../context/AppContext";
import { useLiveStatus } from "../../hooks/useLiveStatus";
import { formatBytes, formatBrainLabel } from "../../utils";
import {
  fullAutoG0HonestyCopy,
  partialMustActCopy,
  partialMustActStartDesc,
  partialMustActStartHint,
} from "../../utils/partialOperatorGates";
import { InfoTooltip } from "../InfoTooltip";
import { StartPhaseGuidance } from "../guidance/PhaseGuidanceBanner";
import { ActionMarker } from "../guidance/ActionMarker";

export function StartTab() {
  const {
    assets,
    selectedAsset,
    setSelectedAsset,
    refreshStartHome,
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
    startRunMode,
    setStartRunMode,
    homunculusVersion,
    setHomunculusVersion,
    homunculusBrains,
    selectedPodcastId,
    setSelectedPodcastId,
    podcastShows,
  } = useApp();
  const sessionLocked = Boolean(runId);
  const selectedBrain = homunculusBrains.find((b) => b.id === homunculusVersion);
  const defaultBrainId = homunculusBrains.find((b) => b.is_default)?.id || "0.2.0";

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
    const isFullAuto = run.meta?.run_mode === "full-auto" || Boolean(run.meta?.full_auto);
    const isPartialAuto =
      run.meta?.run_mode === "partially-accelerated" || Boolean(run.meta?.partial_auto);
    const brainId = run.meta?.homunculus_version || "0.0.0";
    const brainLabel = formatBrainLabel(brainId, run.meta?.homunculus_kind);
    const lockedPodcastId = run.meta?.podcast_id || "";
    const lockedPodcast =
      podcastShows.find((s) => s.id === lockedPodcastId) ||
      (run.meta?.podcast_title
        ? { id: lockedPodcastId, title: run.meta.podcast_title, artwork_url: lockedPodcastId ? `/api/podcasts/${lockedPodcastId}/artwork` : null }
        : null);
    return (
      <main className="view tab-view">
        <section className="panel hero hero-compact">
          <h2>Session in progress</h2>
          <p className="hint">
            Source audio is locked for this session. Continue in Pipeline — use{" "}
            <strong>Menu → Clear session</strong> only when you want to start over.
          </p>
          {isFullAuto ? (
            <p className="hint" data-testid="start-full-auto-active">
              Full-auto is running — G0 is auto-accepted; package and S3 publish are handled
              automatically. Watch Pipeline / Logs for progress.
            </p>
          ) : null}
          {isPartialAuto ? (
            <p className="hint" data-testid="start-partial-auto-active">
              Partially accelerated — {partialMustActCopy()} The guardrail overlay lifts at those
              checkpoints.
            </p>
          ) : null}
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
              <div className="asset-meta" data-testid="start-brain-locked">
                Brain: {brainLabel} (locked)
              </div>
              {lockedPodcast ? (
                <div className="asset-meta start-podcast-locked" data-testid="start-podcast-locked">
                  Podcast: {lockedPodcast.title} (locked)
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

  const fullAutoSelected = startRunMode === "full-auto";
  const partialAutoSelected = startRunMode === "partially-accelerated";
  const manualSelected = startRunMode === "manual";

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
        className="panel panel-compact start-run-mode-panel"
        data-testid="start-run-mode"
        aria-label="Run mode"
      >
        <div className="panel-head">
          <h3>Run mode</h3>
        </div>
        <div
          className="start-run-mode-slider start-run-mode-slider-three"
          role="radiogroup"
          aria-label="Manual, Full-auto, or Partially accelerated"
        >
          <button
            type="button"
            role="radio"
            aria-checked={manualSelected}
            className={`start-run-mode-option${manualSelected ? " selected" : ""}`}
            data-testid="start-mode-manual"
            onClick={() => setStartRunMode("manual")}
          >
            <span className="start-run-mode-title">Manual</span>
            <span className="start-run-mode-desc">
              You review transcript, framing, VO, and publish steps in the GUI.
            </span>
            <span className="start-run-mode-footnote hint sm">
              Full control at every gate.
            </span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={partialAutoSelected}
            className={`start-run-mode-option partial-accelerated${partialAutoSelected ? " selected" : ""}`}
            data-testid="start-mode-partial-auto"
            onClick={() => setStartRunMode("partially-accelerated")}
          >
            <span className="start-run-mode-title">Partially accelerated</span>
            <span className="start-run-mode-desc">{partialMustActStartDesc()}</span>
            <span className="start-run-mode-footnote hint sm">
              Guardrail mode — required stops are G0 + G-Publish; other gates may also pause.
            </span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={fullAutoSelected}
            className={`start-run-mode-option full-auto${fullAutoSelected ? " selected" : ""}`}
            data-testid="start-mode-full-auto"
            onClick={() => setStartRunMode("full-auto")}
          >
            <span className="start-run-mode-title">Full-auto</span>
            <span className="start-run-mode-desc">{fullAutoG0HonestyCopy()}</span>
            <span className="start-run-mode-footnote hint sm">
              G0 auto-accepted; voice-clone consent bypassed.
            </span>
          </button>
        </div>
        {fullAutoSelected ? (
          <p className="hint start-run-mode-warning" data-testid="start-full-auto-hint">
            Full-auto auto-accepts transcript review (G0) and voice-clone consent. Use only when you
            want an unattended end-to-end ship including S3 publish.
          </p>
        ) : null}
        {partialAutoSelected ? (
          <p className="hint start-run-mode-warning" data-testid="start-partial-auto-hint">
            {partialMustActStartHint()}
          </p>
        ) : null}
      </section>
      <section
        className="panel panel-compact start-run-mode-panel"
        data-testid="start-brain"
        aria-label="Mastering brain"
      >
        <div className="panel-head">
          <h3>Brain</h3>
        </div>
        <p className="hint sm" data-testid="start-brain-default-note">
          Default is the <strong>latest homunculus</strong> (
          {homunculusBrains.find((b) => b.is_default)?.id || homunculusVersion}). Original 0.0.0
          remains available.
        </p>
        <div
          className="start-run-mode-slider start-brain-slider"
          role="radiogroup"
          aria-label="Original pipeline or Homunculus"
        >
          {homunculusBrains.map((brain) => {
            const selected = homunculusVersion === brain.id;
            return (
              <button
                key={brain.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`start-run-mode-option${selected ? " selected" : ""}${brain.is_default ? " is-default-brain" : ""}`}
                data-testid={`start-brain-${brain.id.replace(/\./g, "-")}`}
                onClick={() => setHomunculusVersion(brain.id)}
              >
                <span className="start-run-mode-title">
                  {brain.id} — {brain.label}
                  {brain.is_default ? (
                    <span className="start-brain-default-pill">Default</span>
                  ) : null}
                </span>
                <span className="start-run-mode-desc">{brain.summary}</span>
              </button>
            );
          })}
        </div>
        {selectedBrain?.kind !== "homunculus" ? (
          <p className="hint" data-testid="start-brain-original-hint">
            Original 0.0.0 walks analysis then delivery in the order stages were created. Default
            for new runs is Homunculus {defaultBrainId}.
          </p>
        ) : (
          <p className="hint" data-testid="start-brain-homunculus-hint">
            Homunculus {homunculusVersion} runs a fixed seed-order walk with packing, ledger, and
            heal rails. Switch to Original 0.0.0 for the linear walk without those rails.
          </p>
        )}
      </section>
      <section
        className="panel panel-compact start-run-mode-panel"
        data-testid="start-podcast"
        aria-label="Destination podcast"
      >
        <div className="panel-head">
          <h3>Podcast</h3>
        </div>
        <p className="hint sm" data-testid="start-podcast-default-note">
          Choose which RSS feed this run uploads to. Default is{" "}
          <strong>{podcastShows.find((s) => s.is_default)?.title || "Zero Shot Podcast DEMO"}</strong>.
          New S3 / CloudFront origins are created in the terminal, then recorded in the catalog.
        </p>
        <div
          className="start-podcast-slider"
          role="radiogroup"
          aria-label="Destination podcast"
        >
          {podcastShows.map((show) => {
            const selected = selectedPodcastId === show.id;
            const initials = show.title
              .split(/\s+/)
              .filter(Boolean)
              .slice(0, 2)
              .map((w) => w[0]?.toUpperCase() || "")
              .join("");
            return (
              <button
                key={show.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`start-podcast-card${selected ? " selected" : ""}${show.is_default ? " is-default-podcast" : ""}`}
                data-testid={`start-podcast-${show.id}`}
                onClick={() => setSelectedPodcastId(show.id)}
              >
                {show.has_artwork && show.artwork_url ? (
                  <img
                    className="start-podcast-art"
                    src={show.artwork_url}
                    alt=""
                  />
                ) : (
                  <div className="start-podcast-art start-podcast-art-fallback" aria-hidden="true">
                    {initials || "?"}
                  </div>
                )}
                <span className="start-podcast-title">
                  {show.title}
                  {show.is_default ? (
                    <span className="start-brain-default-pill">Default</span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>
      </section>
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
              void refreshStartHome().catch((e) => {
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
                  <ActionMarker status="todo" />{" "}
                  {fullAutoSelected
                    ? "Start Full-auto"
                    : partialAutoSelected
                      ? "Start partially accelerated"
                      : "Start"}
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
