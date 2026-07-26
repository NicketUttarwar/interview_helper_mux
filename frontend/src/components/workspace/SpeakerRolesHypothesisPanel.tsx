import { useCallback, useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";

interface ConversationHypothesis {
  id: string;
  format_class?: string;
  confidence?: number;
  reason?: string;
  speaker_role_map?: Record<string, string>;
}

interface SpeakersArtifact {
  conversation_hypotheses?: ConversationHypothesis[];
  confirmed_conversation_hypothesis_id?: string | null;
  conversation_profile?: {
    format_class_candidate?: string;
    format_confidence?: number;
  };
  gap_sensitivity?: {
    notes?: string;
    priority_gap_types?: string[];
  };
}

export function SpeakerRolesHypothesisPanel() {
  const { runId, refreshRun, showToast } = useApp();
  const [doc, setDoc] = useState<SpeakersArtifact | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    try {
      const res = await api<SpeakersArtifact>(
        `/api/runs/${runId}/artifact?path=${encodeURIComponent("understanding/speakers.json")}`,
      );
      setDoc(res);
    } catch {
      setDoc(null);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const hypotheses = doc?.conversation_hypotheses ?? [];
  const confirmed = doc?.confirmed_conversation_hypothesis_id;
  const needsConfirm = hypotheses.length > 0 && !confirmed;

  if (loading || !needsConfirm) return null;

  const confirm = async (hypothesisId: string) => {
    if (!runId || busy) return;
    setBusy(true);
    traceAction("gui.speaker_roles.confirm_hypothesis", "Confirming conversation interpretation", {
      stage: "speaker_roles",
      meta: { hypothesis_id: hypothesisId },
    });
    try {
      await api(`/api/runs/${runId}/speaker-roles/confirm-hypothesis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hypothesis_id: hypothesisId }),
      });
      showToast("Conversation interpretation confirmed.");
      await load();
      await refreshRun();
    } catch (e) {
      showToast(formatApiError(e, "Hypothesis confirmation failed"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel speaker-hypothesis-panel attention-required" id="speaker-hypothesis-panel">
      <div className="panel-head">
        <h3>Confirm conversation shape</h3>
      </div>
      <p className="hint sm">
        Speaker roles produced multiple interpretations. Pick the layout that matches this
        interview before acknowledging handoff.
      </p>
      <ul className="hypothesis-list">
        {hypotheses.map((hyp) => {
          const rolePreview = hyp.speaker_role_map
            ? Object.entries(hyp.speaker_role_map)
                .map(([sid, role]) => `${sid}=${role}`)
                .join(", ")
            : null;
          return (
            <li key={hyp.id} className="hypothesis-item">
              <div className="hypothesis-head">
                <strong>{hyp.format_class || "unknown format"}</strong>
                {typeof hyp.confidence === "number" ? (
                  <span className="hint sm"> {Math.round(hyp.confidence * 100)}% confidence</span>
                ) : null}
              </div>
              {hyp.reason ? <p className="hint sm">{hyp.reason}</p> : null}
              {rolePreview ? (
                <p className="hint sm">
                  Roles: <code>{rolePreview}</code>
                </p>
              ) : null}
              <button
                type="button"
                className="btn primary sm"
                disabled={busy}
                data-action-id="gui.speaker_roles.confirm_hypothesis"
                onClick={() => void confirm(hyp.id)}
              >
                Confirm interpretation
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
