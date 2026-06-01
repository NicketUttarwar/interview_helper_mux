import { useApp } from "../context/AppContext";

/** Clickable API consent chips — pending providers are buttons, not greyed-out labels. */
export function ApiAccessBar({ compact = false }: { compact?: boolean }) {
  const { apiProviders, apiGrants, promptApiConsent, grantAllPendingApiConsents } =
    useApp();

  if (!apiProviders.length) return null;

  const pending = apiProviders.filter((p) => !apiGrants[p.id]);

  return (
    <div
      className={`api-access-bar${compact ? " compact" : ""}`}
      aria-label="External API access for this browser session"
    >
      <span className="api-access-label">API access</span>
      <div className="api-consent-strip">
        {apiProviders.map((p) => {
          const ok = Boolean(apiGrants[p.id]);
          if (ok) {
            return (
              <span
                key={p.id}
                className="api-consent-chip granted"
                title={`${p.label} allowed for this session`}
              >
                {p.label} ✓
              </span>
            );
          }
          return (
            <button
              key={p.id}
              type="button"
              className="api-consent-chip pending clickable"
              title={p.description || `Allow ${p.label} for this session`}
              onClick={() => void promptApiConsent(p.id)}
            >
              Allow {p.label}
            </button>
          );
        })}
      </div>
      {pending.length > 1 ? (
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => void grantAllPendingApiConsents()}
        >
          Allow all ({pending.length})
        </button>
      ) : null}
      {!compact && pending.length > 0 ? (
        <p className="api-access-hint muted">
          Click a provider before running transcription, analysis, or sound generation.
          Consent applies to this browser session only.
        </p>
      ) : null}
    </div>
  );
}
