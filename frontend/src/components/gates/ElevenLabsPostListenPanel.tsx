import { useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import {
  collectElevenLabsGeneratedAssets,
  latestElevenLabsListenByAsset,
} from "../../utils/profile";
import type { StageInfo } from "../../types";

export function ElevenLabsPostListenPanel({ stage }: { stage: StageInfo }) {
  const { run, refreshRun, showToast } = useApp();
  const inlineRef = useRef<HTMLAudioElement | null>(null);

  const assets = useMemo(
    () =>
      collectElevenLabsGeneratedAssets(
        run?.elevenlabs_generated_assets,
        stage.audio_outputs_present,
      ),
    [run, stage],
  );

  if (!assets.length || !run) return null;

  const listenResults = run.meta?.elevenlabs_listen_results || [];
  const latest = latestElevenLabsListenByAsset(listenResults);

  const submitListen = async (
    assetId: string,
    result: "pass" | "fail",
    note: string,
  ) => {
    const body: Record<string, string> = { asset_id: assetId, result };
    if (note.trim()) body.note = note.trim();
    await api(`/api/runs/${run.run_id}/elevenlabs-prompts/listen-result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    showToast(`Post-listen: ${assetId} → ${result}`);
    await refreshRun();
  };

  const playAsset = async (path: string) => {
    const url = `/api/runs/${run.run_id}/audio?path=${encodeURIComponent(path)}`;
    const player = document.querySelector(".audio-player") as HTMLAudioElement | null;
    const target = player || inlineRef.current;
    if (!target) {
      showToast("Could not play audio — no player available.");
      return;
    }
    target.src = url;
    target.currentTime = 0;
    try {
      await target.play();
    } catch {
      showToast("Could not play audio — check path or open Files tab.");
    }
  };

  return (
    <div className="quality-offer-card el-post-listen-card">
      <audio ref={inlineRef} className="stage-inline-audio hidden" aria-hidden />
      <h4>Post-listen QA (advisory)</h4>
      <p className="muted">
        Listen to each generated asset, then record pass or fail. Optional note is stored
        in <code>run_meta.json</code> and the activity panel.
      </p>
      {assets.map(({ asset_id, path }) => (
        <PostListenRow
          key={asset_id}
          assetId={asset_id}
          path={path}
          prev={latest.get(asset_id)}
          onListen={() => void playAsset(path)}
          onSubmit={submitListen}
        />
      ))}
      {listenResults.length ? (
        <div className="el-post-listen-history">
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
  prev,
  onListen,
  onSubmit,
}: {
  assetId: string;
  path: string;
  prev?: { result?: string; at?: string; note?: string };
  onListen: () => void;
  onSubmit: (assetId: string, result: "pass" | "fail", note: string) => Promise<void>;
}) {
  const prevHtml = prev
    ? `Last: ${prev.result} at ${formatTs(prev.at)}${prev.note ? ` — ${prev.note}` : ""}`
    : "Not reviewed yet";

  return (
    <div className="vo-card el-post-listen-row">
      <h4>{assetId}</h4>
      <p className="muted">
        <code>{path}</code> · <span>{prevHtml}</span>
      </p>
      <div className="stage-audio-actions flow-choice">
        <button type="button" className="btn ghost sm" onClick={onListen}>
          Listen
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
        className="input el-post-listen-note"
        placeholder="e.g. vocals in tail"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
    </div>
  );
}
