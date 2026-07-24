import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatApiError } from "../../utils/safeApi";

/** Speaker volley = conversation between speakers in the podcast timeline (not LLM message packets). */

type SpeakerVolley = {
  speaker_volley_id?: string;
  segment_ids?: string[];
  kind?: string;
  locked?: boolean;
};

type EpisodeStructureDoc = {
  speaker_volleys?: SpeakerVolley[];
  segment_order?: string[];
  hook_reel?: { segment_id?: string | null; repeat_allowed?: boolean };
  integrity?: { ok?: boolean; flags?: string[] };
};

export function SpeakerVolleyTimelinePanel() {
  const { run, showToast } = useApp();
  const [doc, setDoc] = useState<EpisodeStructureDoc | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!run) return;
    setLoading(true);
    void api<{ structure?: EpisodeStructureDoc }>(`/api/runs/${run.run_id}/episode-structure`)
      .then((body) => setDoc(body.structure || null))
      .catch((reason) => {
        setDoc(null);
        showToast(formatApiError(reason, "Speaker volleys"), "error");
      })
      .finally(() => setLoading(false));
  }, [run, showToast]);

  if (!run) return null;
  if (loading) {
    return (
      <div className="quality-offer-card" data-action-id="gui.speaker_volley.view">
        <h4>Speaker volleys</h4>
        <p className="muted sm">Loading conversation units…</p>
      </div>
    );
  }
  const volleys = doc?.speaker_volleys || [];
  return (
    <div className="quality-offer-card" data-action-id="gui.speaker_volley.view">
      <h4>Speaker volleys</h4>
      <p className="muted sm">
        Conversation blocks between speakers in the podcast timeline (not LLM message packets). See
        volley glossary.
      </p>
      {doc?.hook_reel?.segment_id ? (
        <p className="muted sm">
          Cold-open hook: <code>{doc.hook_reel.segment_id}</code>
          {doc.hook_reel.repeat_allowed ? " (repeat allowed)" : ""}
        </p>
      ) : null}
      {doc?.integrity?.ok === false ? (
        <p className="muted sm">Integrity flags: {(doc.integrity.flags || []).join(", ") || "warn"}</p>
      ) : null}
      {!volleys.length ? (
        <p className="muted sm">No speaker volleys detected yet — run episode_structure_compose.</p>
      ) : (
        <ol className="speaker-volley-list">
          {volleys.map((v) => (
            <li key={v.speaker_volley_id || (v.segment_ids || []).join("-")}>
              <strong>{v.speaker_volley_id || "volley"}</strong>{" "}
              <span className="muted sm">
                {v.kind || "turn"} · {(v.segment_ids || []).join(" → ")}
                {v.locked === false ? "" : " · locked"}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
