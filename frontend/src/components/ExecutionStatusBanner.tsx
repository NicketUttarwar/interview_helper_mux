import { useMemo } from "react";
import { useApp } from "../context/AppContext";
import { useJourney } from "../hooks/useJourney";
import { isApiConsentJobPending } from "../utils/checkpoint";

/** What the pipeline is doing right now — running, blocked, or waiting on API consent. */
export function ExecutionStatusBanner() {
  const {
    run,
    jobRunning,
    openActionModal,
    grantAllPendingApiConsents,
    executeJob,
    apiGrants,
  } = useApp();
  const { blocking, runExecuteHint } = useJourney(run);

  const needsApiConsent = useMemo(
    () => isApiConsentJobPending(run, apiGrants),
    [run, apiGrants],
  );

  const missingProviders = run?.job?.missing_api_providers || [];

  if (!run) return null;

  if (jobRunning) {
    const job = run.job;
    return (
      <div className="execution-status-banner running" role="status">
        <span className="execution-status-spinner" aria-hidden />
        <span>
          <strong>Running:</strong>{" "}
          {job?.message || job?.stage || job?.mode || "pipeline stage"}
        </span>
        <span className="muted">Watch the Logs tab for live progress.</span>
      </div>
    );
  }

  if (needsApiConsent) {
    const ungranted = missingProviders.filter((id) => !apiGrants[id]);
    return (
      <div className="execution-status-banner consent" role="status">
        <p>
          <strong>API access needed.</strong>{" "}
          {run.job?.message || "Grant access below, then run again."}
        </p>
        <div className="execution-status-actions">
          {ungranted.length > 0 ? (
            <button
              type="button"
              className="btn primary sm"
              onClick={() => void grantAllPendingApiConsents()}
            >
              Allow required APIs
            </button>
          ) : null}
          {runExecuteHint ? (
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => void executeJob(runExecuteHint.body)}
            >
              Retry: {runExecuteHint.label}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  if (blocking?.blocked && blocking.message) {
    return (
      <div className="execution-status-banner blocked" role="status">
        <p>
          <strong>Your turn:</strong> {blocking.message}
        </p>
        <button type="button" className="btn primary sm" onClick={openActionModal}>
          Open checkpoint
        </button>
      </div>
    );
  }

  if (run.job?.status === "error") {
    return (
      <div className="execution-status-banner error" role="alert">
        <strong>Last job failed.</strong> {run.job.message || "See Logs for details."}
      </div>
    );
  }

  return null;
}
