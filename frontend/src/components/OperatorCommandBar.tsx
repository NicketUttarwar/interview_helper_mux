import { useApp } from "../context/AppContext";
import { useJourney } from "../hooks/useJourney";
import { useOperatorCommand } from "../hooks/useOperatorCommand";
import { findHandoffStage } from "../utils/checkpoint";

/** Persistent operator command bar — running, blocked, handoff, or next step (all tabs). */
export function OperatorCommandBar() {
  const {
    run,
    jobRunning,
    apiGrants,
    executeJob,
    openActionModal,
    selectStage,
    acknowledgeHandoff,
    grantAllPendingApiConsents,
    setActiveTab,
    setPipelineSubTab,
  } = useApp();

  const cmd = useOperatorCommand(run, {
    jobRunning,
    apiGrants,
    onExecute: (body) => void executeJob(body),
    onOpenCheckpoint: (stageId) => {
      if (stageId) void selectStage(stageId);
      openActionModal();
    },
    onAcknowledgeHandoff: () => {
      const hs = findHandoffStage(run);
      if (hs) void selectStage(hs.id).then(() => acknowledgeHandoff());
      else void acknowledgeHandoff();
    },
    onGrantApis: () => void grantAllPendingApiConsents(),
    onGoLogs: () => setActiveTab("logs"),
    onGoStart: () => setActiveTab("start"),
    onGoPipeline: () => {
      setActiveTab("pipeline");
      setPipelineSubTab("stage");
    },
  });

  const { phase } = useJourney(run);

  return (
    <div
      className={`operator-command-bar kind-${cmd.kind}`}
      role="region"
      aria-label="Current action"
      data-testid="operator-command-bar"
    >
      <div className="operator-command-main">
        {cmd.kind === "running" ? (
          <span className="execution-status-spinner" aria-hidden />
        ) : null}
        <p className="operator-command-status">
          {run && phase ? (
            <span className="operator-command-phase muted">{phase}</span>
          ) : null}
          <span>{cmd.statusLine}</span>
        </p>
      </div>
      <div className="operator-command-actions">
        {cmd.secondaryLabel && cmd.onSecondary ? (
          <button
            type="button"
            className="btn ghost sm"
            data-testid="command-secondary"
            onClick={cmd.onSecondary}
          >
            {cmd.secondaryLabel}
          </button>
        ) : null}
        {cmd.primaryLabel && cmd.onPrimary ? (
          <button
            type="button"
            className="btn primary sm"
            data-testid="command-primary"
            disabled={cmd.primaryDisabled}
            onClick={cmd.onPrimary}
          >
            {cmd.primaryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
