import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  getSfxPrompts,
  getSfxUnderSpeechUrl,
  postSfxListenResult,
} from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { MmaudioQaRow } from "../../types";
import { escapeHtml, formatTs } from "../../utils";
import {
  collectSfxGeneratedAssets,
  latestSfxListenByAsset,
} from "../../utils/profile";
import type { StageInfo } from "../../types";

const FAIL_HINTS = [
  "vocals leaked → strengthen negative_prompt",
  "too cinematic → lower CFG / prompt_influence",
  "loop click on bed → simplify texture, check trim",
];

function qaByAsset(rows: MmaudioQaRow[] | undefined): Map<string, MmaudioQaRow> {
  const map = new Map<string, MmaudioQaRow>();
  for (const row of rows || []) {
    if (row?.asset_id) map.set(row.asset_id, row);
  }
  return map;
}

function formatQaMetric(label: string, value: string): string {
  return `${label}: ${value}`;
}

function qaMetricsLine(qa?: MmaudioQaRow): string | null {
  if (!qa) return null;
  const parts: string[] = [];
  if (typeof qa.theme_fit_score === "number") {
    parts.push(formatQaMetric("theme_fit", qa.theme_fit_score.toFixed(2)));
  }
  if (qa.semantic_qa_verdict) {
    parts.push(formatQaMetric("semantic_qa", qa.semantic_qa_verdict));
  }
  if (typeof qa.semantic_similarity === "number") {
    parts.push(formatQaMetric("semantic_sim", qa.semantic_similarity.toFixed(3)));
  }
  if (qa.recommended_action) {
    parts.push(formatQaMetric("action", qa.recommended_action));
  }
  if (typeof qa.spectral_bucket_match === "boolean") {
    parts.push(formatQaMetric("spectral_bucket", qa.spectral_bucket_match ? "match" : "mismatch"));
  }
  return parts.length ? parts.join(" · ") : null;
}

function qaFailedAssets(qaMap: Map<string, MmaudioQaRow>): string[] {
  const ids: string[] = [];
  qaMap.forEach((row, aid) => {
    if (
      row.verdict === "fail" ||
      row.semantic_qa_verdict === "fail" ||
      row.generation_status === "failed" ||
      row.generation_status === "placeholder"
    ) {
      ids.push(aid);
    }
  });
  return ids;
}

export function SfxPostListenPanel({ stage }: { stage: StageInfo }) {
  const { run, config, refreshRun, showToast, advanceFromCheckpoint, jobRunning, actionBusy } =
    useApp();
  const inlineRef = useRef<HTMLAudioElement | null>(null);
  const [listenMode, setListenMode] = useState<"solo" | "under_speech">("solo");
  const [underSpeechSupported, setUnderSpeechSupported] = useState<boolean | null>(null);
  const [mmaudioQa, setMmaudioQa] = useState<MmaudioQaRow[]>([]);

  const assets = useMemo(
    () =>
      collectSfxGeneratedAssets(
        run?.sfx_generated_assets,
        stage.audio_outputs_present,
      ),
    [run, stage],
  );

  useEffect(() => {
    if (!run) return;
    void getSfxPrompts(run.run_id)
      .then((data) => setMmaudioQa(data.mmaudio_qa?.assets || []))
      .catch((e) => {
        setMmaudioQa([]);
        showToast(e instanceof Error ? e.message : "Could not load MMAudio QA", "error");
      });
  }, [run, stage.id]);

  const qaMap = useMemo(() => qaByAsset(mmaudioQa), [mmaudioQa]);

  const listenResults = run?.meta?.sfx_listen_results || [];
  const latest = useMemo(() => latestSfxListenByAsset(listenResults), [listenResults]);
  const failedIds = useMemo(() => {
    const ids: string[] = [];
    latest.forEach((v, aid) => {
      if (v.result === "fail") ids.push(aid);
    });
    return ids;
  }, [latest]);

  const qaFailIds = useMemo(() => qaFailedAssets(qaMap), [qaMap]);

  if (!assets.length || !run) return null;

  const gateState = run.meta?.post_listen_gate_state;
  const gateModeBlock =
    gateState?.mode === "block_mix" ||
    (config as { sound_design?: { post_listen_gate_mode?: string } } | null)?.sound_design
      ?.post_listen_gate_mode === "block_mix" ||
    (config as { sound_design?: { post_listen_gate_mode?: string } } | null)?.sound_design
      ?.post_listen_gate_mode === "block";
  const blockedAssetSet = new Set(gateState?.blocked_assets || []);
  const mixGateBlocked =
    gateModeBlock &&
    (failedIds.length > 0 ||
      qaFailIds.length > 0 ||
      blockedAssetSet.size > 0);

  const allReviewed = assets.every(({ asset_id }) => latest.has(asset_id));
  const canContinue = allReviewed && !mixGateBlocked;

  const submitListen = async (
    assetId: string,
    result: "pass" | "fail",
    note: string,
  ) => {
    try {
      const body: { asset_id: string; result: "pass" | "fail"; note?: string } = {
        asset_id: assetId,
        result,
      };
      if (note.trim()) body.note = note.trim();
      await postSfxListenResult(run.run_id, body);
      showToast(`Post-listen: ${assetId} → ${result}`);
      await refreshRun();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Post-listen save failed", "error");
    }
  };

  const regenerateAsset = async (assetId: string) => {
    try {
      await api(`/api/runs/${run.run_id}/sfx-prompts/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: [assetId] }),
      });
      showToast(`Regenerating ${assetId} via MMAudio…`);
      await refreshRun();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Regenerate failed", "error");
    }
  };

  const autoRefineFailed = async () => {
    try {
      await api(`/api/runs/${run.run_id}/sfx-prompts/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: failedIds, force: true }),
      });
      showToast("Auto-refine completed — review prompts and regenerate.");
      await refreshRun();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Auto-refine failed", "error");
    }
  };

  const passAllAssets = async () => {
    for (const { asset_id } of assets) {
      await submitListen(asset_id, "pass", "e2e auto-pass");
    }
  };

  const playAsset = async (assetId: string, path: string) => {
    const soloUrl = `/api/runs/${run.run_id}/audio?path=${encodeURIComponent(path)}`;
    const underSpeechUrl = getSfxUnderSpeechUrl(run.run_id, assetId);
    const target = inlineRef.current;
    if (!target) {
      showToast("Could not play audio — no player available.");
      return;
    }
    const preferredUrl =
      listenMode === "under_speech" && underSpeechSupported !== false
        ? underSpeechUrl
        : soloUrl;
    target.src = preferredUrl;
    target.currentTime = 0;
    try {
      await target.play();
      if (preferredUrl === underSpeechUrl) setUnderSpeechSupported(true);
    } catch {
      if (preferredUrl === underSpeechUrl) {
        setUnderSpeechSupported(false);
        setListenMode("solo");
        showToast("Speech-under preview unavailable; falling back to solo listen.");
        target.src = soloUrl;
        target.currentTime = 0;
        try {
          await target.play();
          return;
        } catch {
          /* fall through to shared failure toast */
        }
      }
      showToast("Could not play audio — check path or open Files tab.");
    }
  };

  return (
    <div className="quality-offer-card sfx-post-listen-card">
      <audio ref={inlineRef} controls className="stage-inline-audio sfx-post-listen-player" />
      <h4>Post-listen QA (MMAudio)</h4>
      <p className="muted">
        Listen solo, then under speech stem. Fail hints: {FAIL_HINTS.join(" · ")}
      </p>
      {mixGateBlocked ? (
        <div className="sfx-block-mix-banner hint">
          <strong>Mix gate (block_mix):</strong> post-listen or MMAudio QA failures block mix.
          {failedIds.length ? ` Listen fail: ${failedIds.join(", ")}.` : ""}
          {qaFailIds.length ? ` QA fail: ${qaFailIds.join(", ")}.` : ""}
        </div>
      ) : null}
      <div className="flow-choice">
        <button
          type="button"
          className={`btn ghost sm ${listenMode === "solo" ? "active" : ""}`}
          onClick={() => setListenMode("solo")}
        >
          Solo listen
        </button>
        <button
          type="button"
          className={`btn ghost sm ${listenMode === "under_speech" ? "active" : ""}`}
          onClick={() => setListenMode("under_speech")}
          disabled={underSpeechSupported === false}
          title={
            underSpeechSupported === false
              ? "Backend speech-under endpoint unavailable"
              : "Preview under speech stem"
          }
        >
          Under-speech listen
        </button>
      </div>
      {failedIds.length ? (
        <div className="flow-choice">
          <button type="button" className="btn ghost sm" onClick={() => void autoRefineFailed()}>
            Auto-refine failed assets ({failedIds.length})
          </button>
        </div>
      ) : null}
      {assets.length ? (
        <div className="flow-choice">
          <button
            type="button"
            className="btn ghost sm"
            data-testid="sfx-post-listen-pass-all"
            onClick={() => void passAllAssets()}
          >
            Pass all ({assets.length})
          </button>
        </div>
      ) : null}
      {canContinue ? (
        <div className="flow-choice">
          <button
            type="button"
            className="btn primary sm"
            data-testid="sfx-post-listen-continue"
            disabled={jobRunning || actionBusy}
            onClick={() => void advanceFromCheckpoint()}
          >
            Continue pipeline
          </button>
        </div>
      ) : null}
      {assets.map(({ asset_id, path }) => (
        <PostListenRow
          key={asset_id}
          assetId={asset_id}
          path={path}
          qa={qaMap.get(asset_id)}
          prev={latest.get(asset_id)}
          onListen={() => void playAsset(asset_id, path)}
          onSubmit={submitListen}
          onRegenerate={() => void regenerateAsset(asset_id)}
        />
      ))}
      {listenResults.length ? (
        <div className="sfx-post-listen-history">
          <h4 className="muted">Listen history (read-only)</h4>
          <ul className="muted">
            {[...listenResults].reverse().map((e, i) => (
              <li key={i}>
                {formatTs(e.at)} · <strong>{escapeHtml(e.asset_id)}</strong> ·{" "}
                {escapeHtml(e.result)}
                {e.note ? ` — ${escapeHtml(e.note)}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function PostListenRow({
  assetId,
  path,
  qa,
  prev,
  onListen,
  onSubmit,
  onRegenerate,
}: {
  assetId: string;
  path: string;
  qa?: MmaudioQaRow;
  prev?: { result?: string; at?: string; note?: string };
  onListen: () => void;
  onSubmit: (assetId: string, result: "pass" | "fail", note: string) => Promise<void>;
  onRegenerate: () => void;
}) {
  const prevHtml = prev
    ? `Last: ${prev.result} at ${formatTs(prev.at)}${prev.note ? ` — ${prev.note}` : ""}`
    : "Not reviewed yet";
  const qaLine = qaMetricsLine(qa);

  return (
    <div className="vo-card sfx-post-listen-row">
      <h4>{assetId}</h4>
      <p className="muted">
        <code>{path}</code> · <span>{prevHtml}</span>
      </p>
      {qaLine ? (
        <p className="muted sm sfx-qa-metrics">
          {qaLine}
          {qa?.verdict ? ` · verdict ${qa.verdict}` : ""}
        </p>
      ) : null}
      <div className="stage-audio-actions flow-choice">
        <button type="button" className="btn ghost sm" onClick={onListen}>
          Listen
        </button>
        <button type="button" className="btn ghost sm" onClick={onRegenerate}>
          Regenerate
        </button>
      </div>
      <PostListenNoteButtons assetId={assetId} onSubmit={onSubmit} />
    </div>
  );
}

function PostListenNoteButtons({
  assetId,
  onSubmit,
}: {
  assetId: string;
  onSubmit: (assetId: string, result: "pass" | "fail", note: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  return (
    <div style={{ width: "100%" }}>
      <div className="stage-audio-actions flow-choice">
        <button type="button" className="btn primary sm" onClick={() => void onSubmit(assetId, "pass", note)}>
          Pass
        </button>
        <button type="button" className="btn ghost sm" onClick={() => void onSubmit(assetId, "fail", note)}>
          Fail
        </button>
      </div>
      <label className="tr-label">Note (optional)</label>
      <input
        type="text"
        className="input sfx-post-listen-note"
        placeholder="e.g. vocals in tail, too cinematic"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
    </div>
  );
}
