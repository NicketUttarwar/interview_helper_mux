import { useMemo, useState } from "react";
import { useApp } from "../context/AppContext";
import { formatTs } from "../utils";

export function StatusHeader() {
  const {
    run,
    selectedStage,
    alertsMuted,
    apiProviders,
    apiGrants,
    setAlertsMuted,
    revokeAllApiConsents,
    pendingActionCount,
    actionSummary,
    openActionModal,
    menuOpen,
    setMenuOpen,
    clearSession,
  } = useApp();

  const [showApiPopover, setShowApiPopover] = useState(false);

  const jobLabel = useMemo(() => {
    const job = run?.job;
    if (job?.status === "running_with_warnings") {
      return { text: `Running (warnings) ${job.stage || job.mode}`, cls: "running_with_warnings" };
    }
    if (job?.status === "running") {
      return { text: `Running ${job.stage || job.mode}`, cls: "running" };
    }
    if (job?.status === "gate" || job?.status === "needs_operator") {
      return { text: "Action required", cls: "action" };
    }
    if (job?.status === "error") {
      return { text: "Error", cls: "error" };
    }
    return {
      text: job?.status === "complete" ? "Complete" : "Idle",
      cls: "idle",
    };
  }, [run]);

  const precleanWarnings = run?.job?.preclean_warnings;

  return (
    <header className="status-header status-header-compact">
      <div className="status-grid status-grid-compact">
        <div className="status-cell">
          <span className="status-label">Execution</span>
          <span className="status-value">
            {run
              ? run.meta?.execution_number
                ? `#${run.meta.execution_number} · ${run.run_id}`
                : run.run_id
              : "—"}
          </span>
        </div>
        <div className="status-cell">
          <span className="status-label">Stage</span>
          <span className="status-value">{selectedStage?.title || "—"}</span>
        </div>
        <div className="status-cell">
          <span className="status-label">Job</span>
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
                  className="btn ghost sm block"
                  onClick={() => setShowApiPopover(!showApiPopover)}
                >
                  API access status
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

      {showApiPopover && apiProviders.length > 0 ? (
        <div className="api-consent-strip api-consent-popover" aria-label="API access">
          {apiProviders.map((p) => {
            const ok = Boolean(apiGrants[p.id]);
            return (
              <span
                key={p.id}
                className={`api-consent-chip ${ok ? "granted" : "pending"}`}
              >
                {p.label} {ok ? "✓" : "—"}
              </span>
            );
          })}
        </div>
      ) : null}

      {precleanWarnings?.length ? (
        <div className="preclean-warnings-banner compact-banner" role="status">
          {precleanWarnings
            .map((w) => `Pre-clean (${w.checkpoint}) — ${w.stage}`)
            .join(" · ")}
        </div>
      ) : null}
    </header>
  );
}
