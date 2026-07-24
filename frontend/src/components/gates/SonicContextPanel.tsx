import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { SonicContextData } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import {
  sonicTagProvenanceText,
  summarizeSonicContextScenario,
} from "../../utils/profile";

const SONIC_CONTEXT_PATH = "understanding/sonic_context.json";

type SoundscapeSummary = {
  underscore_policy?: string;
  pace_class?: string;
  sfx_density?: Record<string, number>;
  cue_slot_ids?: string[];
  verify_verdict?: string;
};

type EpisodeStructureSummary = {
  axes?: { atlas_bucket?: string; format_class?: string };
  slot_plan?: { component_id?: string; gate?: string }[];
  omit_high_profile?: string[];
  hook_reel?: { segment_id?: string | null; repeat_allowed?: boolean };
  speaker_volleys?: { speaker_volley_id?: string }[];
  integrity_ok?: boolean;
};

export function SonicContextPanel() {
  const { run, showToast } = useApp();
  const [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<SonicContextData | null>(null);
  const [soundscape, setSoundscape] = useState<SoundscapeSummary | null>(null);
  const [episodeStructure, setEpisodeStructure] = useState<EpisodeStructureSummary | null>(null);

  useEffect(() => {
    if (!run) return;
    setLoading(true);
    void api<SonicContextData>(
      `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent(SONIC_CONTEXT_PATH)}`,
    )
      .then((data) => setDoc(data))
      .catch((reason) => {
        setDoc(null);
        showToast(formatApiError(reason, "Sonic context"), "error");
      })
      .finally(() => setLoading(false));
    void api<{ summary?: SoundscapeSummary; report?: { verdict?: string } }>(
      `/api/runs/${run.run_id}/soundscape-policy`,
    )
      .then((body) => {
        const summary = body.summary || null;
        if (summary && body.report?.verdict) {
          summary.verify_verdict = body.report.verdict;
        }
        setSoundscape(summary);
      })
      .catch(() => setSoundscape(null));
    void api<{ summary?: EpisodeStructureSummary }>(
      `/api/runs/${run.run_id}/episode-structure`,
    )
      .then((body) => setEpisodeStructure(body.summary || null))
      .catch(() => setEpisodeStructure(null));
  }, [run, showToast]);

  if (!run) return null;
  if (loading) {
    return (
      <div className="quality-offer-card">
        <h4>Sonic context</h4>
        <div className="gate-loading-skeleton panel-inset" aria-busy>
          <span className="spinner-inline" aria-hidden /> Loading sonic context…
        </div>
      </div>
    );
  }
  if (!doc) {
    return (
      <div className="quality-offer-card">
        <h4>Sonic context</h4>
        <p className="muted sm">Run sound planning to generate sonic context.</p>
      </div>
    );
  }

  return (
    <div className="quality-offer-card">
      <h4>Sonic context</h4>
      <p className="muted sm">{summarizeSonicContextScenario(doc)}</p>
      <p className="muted sm">
        Scenario bucket: <strong>{doc.scenario?.atlas_bucket || "—"}</strong>
      </p>
      <p className="muted sm">
        Mix policy: underscore <strong>{doc.mix_policy?.underscore_policy || "—"}</strong>, max
        assets flow1/flow2{" "}
        <strong>
          {doc.mix_policy?.adaptive_max_assets_flow1 ?? "—"}/
          {doc.mix_policy?.adaptive_max_assets_flow2 ?? "—"}
        </strong>
      </p>
      {soundscape ? (
        <p className="muted sm" data-action-id="gui.soundscape.view">
          Soundscape policy: underscore <strong>{soundscape.underscore_policy || "—"}</strong>,
          pace <strong>{soundscape.pace_class || "—"}</strong>, cue slots{" "}
          <strong>{soundscape.cue_slot_ids?.length ?? 0}</strong>
          {soundscape.verify_verdict
            ? `, verify ${soundscape.verify_verdict}`
            : ""}
        </p>
      ) : null}
      {episodeStructure ? (
        <p className="muted sm" data-action-id="gui.episode_structure.view">
          Episode structure: atlas{" "}
          <strong>{episodeStructure.axes?.atlas_bucket || "—"}</strong>, slots{" "}
          <strong>{episodeStructure.slot_plan?.length ?? 0}</strong>
          {(episodeStructure.omit_high_profile || []).length
            ? `, omitted ${episodeStructure.omit_high_profile.join(", ")}`
            : ""}
          {episodeStructure.hook_reel?.repeat_allowed
            ? `, hook reel ${episodeStructure.hook_reel.segment_id || "on"}`
            : ""}
          {episodeStructure.speaker_volleys?.length
            ? `, speaker volleys ${episodeStructure.speaker_volleys.length}`
            : ""}
          {episodeStructure.integrity_ok === false ? ", integrity warn" : ""}
        </p>
      ) : null}
      <table className="placement-qa-table">
        <thead>
          <tr>
            <th>Tag</th>
            <th>Kind</th>
            <th>Keywords</th>
            <th>Provenance</th>
          </tr>
        </thead>
        <tbody>
          {(doc.tag_registry || []).map((tag) => (
            <tr key={tag.tag_id}>
              <td>
                <code>{tag.tag_id}</code>
              </td>
              <td>{tag.kind || "—"}</td>
              <td>{(tag.keywords || []).join(", ") || "—"}</td>
              <td className="muted sm">{sonicTagProvenanceText(tag)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(doc.avoid_hard || []).length ? (
        <p className="muted sm">avoid_hard: {(doc.avoid_hard || []).join(" · ")}</p>
      ) : null}
    </div>
  );
}
