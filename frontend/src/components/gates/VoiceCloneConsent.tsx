import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";

type CloneScope = "cold_open" | "bridges" | "outro";
type Disclosure = "none" | "show_notes" | "in_audio";

const SCOPE_LABELS: Record<CloneScope, string> = {
  cold_open: "Cold open narration",
  bridges: "Inter-segment bridges",
  outro: "Closing narration",
};

const DISCLOSURE_LABELS: Record<Disclosure, string> = {
  none: "No disclosure",
  show_notes: "Disclose in show notes",
  in_audio: "Spoken disclosure in outro",
};

interface ConsentRecord {
  speaker_id?: string | null;
  granted?: boolean;
  granted_at?: string | null;
  scopes?: string[];
  disclosure?: Disclosure;
  revoked_at?: string | null;
}

interface ConsentPayload {
  voice_clone_consent?: ConsentRecord;
  voice_clone_consent_active?: boolean;
  voice_clone_available_scopes?: CloneScope[];
  voice_clone_disclosure_options?: Disclosure[];
  voice_clone_mode?: string;
}

export function VoiceCloneConsent() {
  const { runId, showToast } = useApp();
  const [data, setData] = useState<ConsentPayload | null>(null);
  const [scopes, setScopes] = useState<CloneScope[]>(["bridges"]);
  const [disclosure, setDisclosure] = useState<Disclosure>("none");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<ConsentPayload>(`/api/runs/${runId}/voice-clone-consent`);
      setData(res);
      const granted = res.voice_clone_consent?.scopes;
      if (granted?.length) setScopes(granted as CloneScope[]);
      if (res.voice_clone_consent?.disclosure) setDisclosure(res.voice_clone_consent.disclosure);
    } catch (e) {
      showToast(formatApiError(e, "Load clone consent"), "error");
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const grant = async () => {
    if (!runId || busy || !scopes.length) return;
    setBusy(true);
    traceAction("gui.voice_clone.grant", "Granting voice clone consent", {
      meta: { scopes },
    });
    try {
      await api(`/api/runs/${runId}/voice-clone-consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scopes, disclosure }),
      });
      showToast("Clone consent recorded.");
      await load();
    } catch (e) {
      showToast(formatApiError(e, "Grant clone consent"), "error");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!runId || busy) return;
    setBusy(true);
    traceAction("gui.voice_clone.revoke", "Revoking voice clone consent", {});
    try {
      await api(`/api/runs/${runId}/voice-clone-consent`, { method: "DELETE" });
      showToast("Clone consent revoked.", "warning");
      await load();
    } catch (e) {
      showToast(formatApiError(e, "Revoke clone consent"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!data) return null;

  const consent = data.voice_clone_consent ?? {};
  const active = Boolean(data.voice_clone_consent_active);
  const availableScopes = data.voice_clone_available_scopes ?? ["cold_open", "bridges", "outro"];

  if (active) {
    return (
      <section className="panel-inset" data-testid="voice-clone-consent">
        <p className="hint sm">
          ✓ Clone consent recorded for {consent.speaker_id} — scopes:{" "}
          {(consent.scopes ?? []).map((s) => SCOPE_LABELS[s as CloneScope] ?? s).join(", ")}.{" "}
          {DISCLOSURE_LABELS[(consent.disclosure ?? "none") as Disclosure]}.
        </p>
        <button type="button" className="btn sm" disabled={busy} onClick={() => void revoke()}>
          Revoke consent
        </button>
      </section>
    );
  }

  return (
    <section className="panel-inset" data-testid="voice-clone-consent">
      <h4>Clone consent</h4>
      <p className="hint sm">
        Approving a reference sample is not permission to synthesize it. Choose where this voice may
        speak. Guest voices can never be cloned.
      </p>
      <ul className="pickup-speaker-list">
        {availableScopes.map((scope) => (
          <li key={scope} className="pickup-speaker-card vo-card">
            <label>
              <input
                type="checkbox"
                checked={scopes.includes(scope)}
                disabled={busy}
                onChange={() =>
                  setScopes((prev) =>
                    prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
                  )
                }
              />
              <span className="muted sm">{SCOPE_LABELS[scope] ?? scope}</span>
            </label>
          </li>
        ))}
      </ul>
      <label className="hint sm">
        Disclosure
        <select
          value={disclosure}
          disabled={busy}
          onChange={(e) => setDisclosure(e.target.value as Disclosure)}
        >
          {(data.voice_clone_disclosure_options ?? ["none", "show_notes", "in_audio"]).map((d) => (
            <option key={d} value={d}>
              {DISCLOSURE_LABELS[d] ?? d}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="btn primary sm"
        data-testid="grant-clone-consent"
        disabled={busy || !scopes.length}
        onClick={() => void grant()}
      >
        Grant clone consent
      </button>
    </section>
  );
}
