import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import type { ElevenLabsPromptRow, ElevenLabsPromptsResponse, StageInfo } from "../../types";

export function ElevenLabsPromptReviewPanel({ stage }: { stage: StageInfo }) {
  const { run, refreshRun, selectStage, showToast } = useApp();
  const [data, setData] = useState<ElevenLabsPromptsResponse | null>(null);
  const [edits, setEdits] = useState<ElevenLabsPromptRow[]>([]);

  useEffect(() => {
    if (!run) return;
    void api<ElevenLabsPromptsResponse>(
      `/api/runs/${run.run_id}/elevenlabs-prompts`,
    ).then((d) => {
      setData(d);
      setEdits(d.prompts || []);
    });
  }, [run, stage.id]);

  if (!data) return null;

  const approved = Boolean(data.review?.approved);
  const reviewRequired = Boolean(data.review_required);

  const updateRow = (idx: number, patch: Partial<ElevenLabsPromptRow>) => {
    setEdits((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const saveEdits = async () => {
    if (!run) return;
    await api(`/api/runs/${run.run_id}/elevenlabs-prompts`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: "sound_design/elevenlabs_prompts.json",
        data: { prompts: edits },
        invalidate_from: "elevenlabs_prompt_craft",
      }),
    });
    showToast("Prompt edits saved; approval reset.");
    await refreshRun();
    await selectStage("elevenlabs_prompt_craft");
  };

  const approve = async () => {
    if (!run) return;
    await api(`/api/runs/${run.run_id}/elevenlabs-prompts/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: "operator_gui" }),
    });
    showToast("Prompts approved.");
    await refreshRun();
    await selectStage("elevenlabs_prompt_craft");
  };

  return (
    <>
      <div className="quality-offer-card">
        <p className="hint">
          <strong>G1.5 prompt review:</strong> review or edit crafted prompts before SFX
          generation.
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
        edits.map((row, idx) => (
          <div key={idx} className="vo-card" data-idx={idx}>
            <h4>
              {row.asset_id || `asset_${idx + 1}`} · {row.role || "unknown"}
            </h4>
            <div className="asset-meta">
              duration {Number(row.duration_seconds || 0).toFixed(2)}s
            </div>
            <label className="tr-label">Prompt influence (0–1)</label>
            <input
              className="input el-prompt-influence"
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
              className="tr-textarea el-prompt-text"
              rows={3}
              value={row.elevenlabs_prompt || ""}
              onChange={(e) =>
                updateRow(idx, { elevenlabs_prompt: e.target.value })
              }
            />
            <label className="tr-label">Negative prompt</label>
            <input
              className="input el-negative-prompt"
              value={row.negative_prompt || ""}
              onChange={(e) =>
                updateRow(idx, { negative_prompt: e.target.value })
              }
            />
          </div>
        ))
      )}
      {(data.warnings || []).length ? (
        <ul className="muted">
          {data.warnings!.map((w, i) => (
            <li key={i}>{escapeHtml(w)}</li>
          ))}
        </ul>
      ) : null}
      <div className="flow-choice">
        <button type="button" className="btn ghost sm" onClick={() => void saveEdits()}>
          Save edits
        </button>
        <button
          type="button"
          className="btn primary sm"
          disabled={!edits.length}
          onClick={() => void approve()}
        >
          Approve prompts
        </button>
      </div>
    </>
  );
}
