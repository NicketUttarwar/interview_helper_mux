import { useApp } from "../context/AppContext";

export function ApiConsentModal() {
  const { pendingConsentProvider, apiProviders, resolveApiConsent } = useApp();

  if (!pendingConsentProvider) return null;

  const info = apiProviders.find((p) => p.id === pendingConsentProvider);

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card panel">
        <h3>{info ? `Allow ${info.label}?` : "Allow external API?"}</h3>
        <p className="lead">{info?.description || ""}</p>
        <p className="muted">{info?.cost_hint || ""}</p>
        <div className="modal-actions">
          <button
            type="button"
            className="btn ghost"
            onClick={() => void resolveApiConsent(false)}
          >
            Not now
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => void resolveApiConsent(true)}
          >
            Allow for this session
          </button>
        </div>
      </div>
    </div>
  );
}
