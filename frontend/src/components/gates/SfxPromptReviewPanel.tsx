import { useEffect, useMemo, useRef, useState } from "react";
import { api, getSfxPrompts } from "../../api/client";
import { InfoTooltip } from "../InfoTooltip";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import { registerStepPrimaryPrep } from "../../utils/stepPrimaryPrep";
import { summarizeSonicContextScenario } from "../../utils/profile";
import type { MmaudioQaRow, SfxPromptRow, SfxPromptsResponse, StageInfo } from "../../types";

const MMAUDIO_VARIANTS = [
  "small_16k",
  "small_44k",
  "medium_44k",
  "large_44k",
  "large_44k_v2",
] as const;

function qaTooltipText(row?: MmaudioQaRow): string | null {
  if (!row) return null;
  const parts: string[] = [];
  if (row.verdict) parts.push(`verdict: ${row.verdict}`);
  if (row.reasons?.length) parts.push(row.reasons.join("; "));
  if (typeof row.theme_fit_score === "number") {
    parts.push(`theme_fit: ${row.theme_fit_score.toFixed(2)}`);
  }
  if (row.semantic_qa_verdict) parts.push(`semantic_qa: ${row.semantic_qa_verdict}`);
  if (typeof row.semantic_similarity === "number") {
    parts.push(`semantic_sim: ${row.semantic_similarity.toFixed(3)}`);
  }
  if (row.recommended_action) parts.push(`recommended: ${row.recommended_action}`);
  if (typeof row.spectral_bucket_match === "boolean") {
    parts.push(`spectral_bucket: ${row.spectral_bucket_match ? "match" : "mismatch"}`);
  }
  return parts.length ? parts.join(" · ") : null;
}

export function SfxPromptReviewPanel({ stage }: { stage: StageInfo }) {
  const { run, refreshRun } = useApp();
  const [data, setData] = useState<SfxPromptsResponse | null>(null);
  const [edits, setEdits] = useState<SfxPromptRow[]>([]);
  const editsRef = useRef(edits);
  editsRef.current = edits;

  useEffect(() => {
    if (!run) return;
    void getSfxPrompts(run.run_id).then((d) => {
      setData(d);
      setEdits(d.prompts || []);
    });
  }, [run, stage.id]);

  const qaByAsset = useMemo(() => {
    const map = new Map<string, MmaudioQaRow>();
    for (const row of data?.mmaudio_qa?.assets || []) {
      if (row?.asset_id) map.set(row.asset_id, row);
    }
    return map;
  }, [data?.mmaudio_qa]);

  useEffect(() => {
    registerStepPrimaryPrep("sfx_prompt_review", async () => {
      if (!run || !editsRef.current.length) return;
      const original = data?.prompts || [];
      const changed =
        JSON.stringify(editsRef.current) !== JSON.stringify(original);
      if (!changed) return;
      await api(`/api/runs/${run.run_id}/sfx-prompts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "sound_design/sfx_prompts.json",
          data: { prompts: editsRef.current },
          invalidate_from: "sfx_prompt_craft",
        }),
      });
      await refreshRun();
    });
    return () => registerStepPrimaryPrep("sfx_prompt_review", null);
  }, [run, data?.prompts, refreshRun]);

  if (!data) return null;

  const approved = Boolean(data.review?.approved);
  const reviewRequired = Boolean(data.review_required);
  const sonicSummary = summarizeSonicContextScenario(data.sonic_context ?? null);

  const updateRow = (idx: number, patch: Partial<SfxPromptRow>) => {
    setEdits((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  return (
    <>
      <div className="quality-offer-card">
        <p className="hint">
          <strong>G1.5 prompt review:</strong> review or edit MMAudio text-to-audio prompts before
          local SFX generation.
        </p>
        <p className="muted sm sfx-sonic-header">
          <strong>Sonic context:</strong> {escapeHtml(sonicSummary)}
        </p>
        <p className="muted">
          Approval status:{" "}
          {approved
            ? `approved by ${escapeHtml(data.review?.approved_by || "operator")} at ${formatTs(data.review?.approved_at)}`
            : "pending approval"}
          {reviewRequired ? " (required before generate)" : " (optional)"}.
        </p>
      </div>
      {!edits.length ? (
        <p className="empty-state">No crafted prompts yet. Run this stage first.</p>
      ) : (
        edits.map((row, idx) => {
          const assetId = row.asset_id || `asset_${idx + 1}`;
          const qa = qaByAsset.get(row.asset_id || "");
          const qaTip = qaTooltipText(qa);
          return (
            <div key={idx} className="vo-card" data-idx={idx}>
              <h4>
                {assetId} · {row.role || "unknown"}
                {qa?.verdict ? (
                  <>
                    <span className="badge" style={{ marginLeft: "0.5rem" }}>
                      QA {qa.verdict}
                    </span>
                    {qaTip ? (
                      <InfoTooltip text={qaTip} label={`QA details for ${assetId}`} />
                    ) : null}
                  </>
                ) : null}
              </h4>
              <div className="asset-meta">
                duration {Number(row.duration_seconds || 0).toFixed(2)}s
              </div>
              <label className="tr-label">Prompt influence (0–1)</label>
              <input
                className="input sfx-prompt-influence"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={Number(row.prompt_influence ?? 0.35).toFixed(2)}
                onChange={(e) =>
                  updateRow(idx, { prompt_influence: Number(e.target.value) })
                }
              />
              <label className="tr-label">Prompt</label>
              <textarea
                className="tr-textarea sfx-prompt-text"
                rows={3}
                value={row.sfx_prompt || ""}
                onChange={(e) =>
                  updateRow(idx, { sfx_prompt: e.target.value })
                }
              />
              <label className="tr-label">Negative prompt (MMAudio API)</label>
              <input
                className="input sfx-negative-prompt"
                value={row.negative_prompt || ""}
                onChange={(e) =>
                  updateRow(idx, { negative_prompt: e.target.value })
                }
              />
              <details className="mmaudio-advanced-fields">
                <summary className="muted sm">Advanced MMAudio params</summary>
                <label className="tr-label">MMAudio variant</label>
                <select
                  className="select"
                  value={row.mmaudio_variant || ""}
                  onChange={(e) =>
                    updateRow(idx, {
                      mmaudio_variant: e.target.value || undefined,
                    })
                  }
                >
                  <option value="">— default —</option>
                  {MMAUDIO_VARIANTS.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
                <label className="tr-label">CFG strength (2–8)</label>
                <input
                  className="input"
                  type="number"
                  min={2}
                  max={8}
                  step={0.1}
                  value={row.cfg_strength ?? ""}
                  onChange={(e) =>
                    updateRow(idx, {
                      cfg_strength: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
                <label className="tr-label">Num steps</label>
                <input
                  className="input"
                  type="number"
                  min={10}
                  max={50}
                  value={row.num_steps ?? ""}
                  onChange={(e) =>
                    updateRow(idx, {
                      num_steps: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
                <label className="tr-label">Seed</label>
                <input
                  className="input"
                  type="number"
                  value={row.seed ?? ""}
                  onChange={(e) =>
                    updateRow(idx, {
                      seed: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
              </details>
            </div>
          );
        })
      )}
      {(data.warnings || []).length ? (
        <ul className="muted">
          {data.warnings!.map((w, i) => (
            <li key={i}>{escapeHtml(w)}</li>
          ))}
        </ul>
      ) : null}
      <p className="hint sm">
        Use <strong>Approve prompts</strong> at the bottom of this step to save edits and continue.
      </p>
    </>
  );
}
