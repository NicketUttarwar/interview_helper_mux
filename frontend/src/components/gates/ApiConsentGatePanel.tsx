import { useApp } from "../../context/AppContext";

/** Shown in the operator modal when the last job stopped for missing API consent. */
export function ApiConsentGatePanel() {
  const { run, apiProviders, apiGrants, promptApiConsent, grantAllPendingApiConsents } =
    useApp();

  const missing =
    run?.job?.missing_api_providers?.filter((id) => !apiGrants[id]) ||
    apiProviders.filter((p) => !apiGrants[p.id]).map((p) => p.id);

  if (!missing.length) return null;

  return (
    <div className="gate-actions api-consent-gate panel">
      <h4>Allow external APIs</h4>
      <p className="hint">
        The pipeline cannot run until you approve API use for this browser session.
        {run?.job?.message ? ` ${run.job.message}` : ""}
      </p>
      <ul className="api-consent-gate-list">
        {missing.map((id) => {
          const info = apiProviders.find((p) => p.id === id);
          return (
            <li key={id}>
              <div>
                <strong>{info?.label || id}</strong>
                {info?.cost_hint ? (
                  <p className="muted">{info.cost_hint}</p>
                ) : null}
              </div>
              <button
                type="button"
                className="btn primary sm"
                onClick={() => void promptApiConsent(id)}
              >
                Allow
              </button>
            </li>
          );
        })}
      </ul>
      {missing.length > 1 ? (
        <button
          type="button"
          className="btn ghost block"
          onClick={() => void grantAllPendingApiConsents()}
        >
          Allow all ({missing.length})
        </button>
      ) : null}
    </div>
  );
}
