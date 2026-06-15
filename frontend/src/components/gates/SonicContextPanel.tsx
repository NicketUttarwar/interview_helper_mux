import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { SonicContextData } from "../../types";
import {
  sonicTagProvenanceText,
  summarizeSonicContextScenario,
} from "../../utils/profile";

const SONIC_CONTEXT_PATH = "understanding/sonic_context.json";

export function SonicContextPanel() {
  const { run } = useApp();
  const [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<SonicContextData | null>(null);

  useEffect(() => {
    if (!run) return;
    setLoading(true);
    void api<SonicContextData>(
      `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent(SONIC_CONTEXT_PATH)}`,
    )
      .then((data) => setDoc(data))
      .catch(() => setDoc(null))
      .finally(() => setLoading(false));
  }, [run]);

  if (!run) return null;
  if (loading) {
    return (
      <div className="quality-offer-card">
        <h4>Sonic context</h4>
        <p className="muted sm">Loading sonic context…</p>
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
