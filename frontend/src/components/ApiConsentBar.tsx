import { useApp } from "../context/AppContext";
import { isApiConsentJobPending } from "../utils/checkpoint";

export function ApiConsentBar() {
  const { run, apiGrants, apiProviders, grantApiConsent, jobRunning } = useApp();
  const pending = isApiConsentJobPending(run, apiGrants);
  const missing = run?.job?.missing_api_providers ?? [];

  const showBar =
    pending ||
    apiProviders.some((p) => !apiGrants[p.id] && (missing.length === 0 || missing.includes(p.id)));

  if (!showBar) return null;

  return (
    <div className="api-consent-strip api-access-bar" role="region" aria-label="External API access">
      <span className="hint sm">External APIs:</span>
      {apiProviders.map((provider) => {
        const granted = Boolean(apiGrants[provider.id]);
        const required =
          pending &&
          (missing.includes(provider.id) ||
            String(run?.job?.message || "")
              .toLowerCase()
              .includes(provider.label.toLowerCase()));
        return (
          <button
            key={provider.id}
            type="button"
            className={`api-consent-chip clickable${granted ? " granted" : " pending"}${required ? " required" : ""}`}
            title={provider.description}
            disabled={jobRunning}
            onClick={() => void grantApiConsent(provider.id, !granted)}
          >
            {provider.label}
            {granted ? " ✓" : " — grant"}
          </button>
        );
      })}
      {pending && run?.job?.message ? (
        <span className="hint sm api-consent-gate-hint">{run.job.message}</span>
      ) : null}
    </div>
  );
}
