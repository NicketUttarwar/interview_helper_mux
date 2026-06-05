import { useMemo } from "react";
import { useApp } from "../context/AppContext";
import { formatTs } from "../utils";
import { ApiAccessBar } from "./ApiAccessBar";
import { stageTitleForId } from "../utils/checkpoint";

export function StatusHeader() {
  const {
    run,
    alertsMuted,
    setAlertsMuted,
    revokeAllApiConsents,
    pendingActionCount,
    actionSummary,
    openActionModal,
    menuOpen,
    setMenuOpen,
    clearSession,
    jobRunning,
  } = useApp();

  const jobLabel = useMemo(() => {
    const job = run?.job;
    const runningStage =
      stageTitleForId(run?.stages, job?.stage) ||
      job?.stage?.replace(/_/g, " ") ||
      job?.mode;
    if (jobRunning || job?.status === "running" || job?.status === "running_with_warnings") {
      return { text: runningStage ? `Running: ${runningStage}` : "Running", cls: "running" };
    }
    if (job?.status === "gate" || job?.status === "needs_operator") {
      return { text: "Needs you", cls: "action" };
    }
    if (job?.status === "error") return { text: "Failed", cls: "error" };
    if (job?.status === "complete") return { text: "Complete", cls: "idle" };
    return { text: "Idle", cls: "idle" };
  }, [run, jobRunning]);

  const precleanWarnings = run?.job?.preclean_warnings;

  return (
    <header className="status-header-wrap">
      <div className="status-header status-header-compact">
        <div className="status-grid status-grid-compact">
          <div className="status-cell">
            <span className="status-label">Run</span>
            <span className="status-value">
              {run
                ? run.meta?.execution_number
                  ? `#${run.meta.execution_number}`
                  : run.run_id
                : "None"}
            </span>
          </div>
          <div className="status-cell">
            <span className="status-label">Status</span>
            <span className={`status-value ${jobLabel.cls}`}>{jobLabel.text}</span>
          </div>
          <div className="status-cell">
            <span className="status-label">Updated</span>
            <span className="status-value muted">{formatTs(run?.meta?.updated_at)}</span>
          </div>
          <div className="status-cell actions">
            {pendingActionCount > 0 ? (
              <button
                type="button"
                className="btn primary sm action-badge-btn"
                onClick={openActionModal}
                title={actionSummary || "Action required"}
              >
                Action ({pendingActionCount})
              </button>
            ) : null}
            <button
              type="button"
              className={`btn ghost sm${alertsMuted ? " muted-active" : ""}`}
              title="Mute attention sounds"
              onClick={() => setAlertsMuted(!alertsMuted)}
            >
              {alertsMuted ? "Unmute" : "Mute"}
            </button>
            <div className="header-menu-wrap">
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => setMenuOpen(!menuOpen)}
                aria-expanded={menuOpen}
              >
                Menu
              </button>
              {menuOpen ? (
                <div className="header-menu panel">
                  <button type="button" className="btn ghost sm block" onClick={revokeAllApiConsents}>
                    Revoke API access
                  </button>
                  <button
                    type="button"
                    className="btn danger ghost sm block"
                    onClick={() => void clearSession()}
                  >
                    Clear session
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <ApiAccessBar compact />

        {precleanWarnings?.length ? (
          <div className="preclean-warnings-banner compact-banner" role="status">
            {precleanWarnings
              .map((w) => `Pre-clean (${w.checkpoint}) — ${w.stage}`)
              .join(" · ")}
          </div>
        ) : null}
      </div>
    </header>
  );
}
