import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { StageInfo } from "../../types";
import {
  shouldAdvanceAfterGatePost,
  shouldBlockOperatorActionsForJob,
} from "../../utils/partialAcceleratedGuard";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";
import { ArtifactAudio } from "../shared/ArtifactAudio";
import { VoiceCloneConsent } from "./VoiceCloneConsent";

interface VoiceSegment {
  start_ms?: number;
  end_ms?: number;
  quote?: string;
  score?: number;
  selected?: boolean;
  clip_path?: string | null;
}

interface VoiceReferencePayload {
  speaker_id?: string | null;
  segments?: VoiceSegment[];
  approved?: boolean;
  ref_quality?: {
    duration_sec?: number;
    avg_clip_score?: number;
    warnings?: string[];
  } | null;
}

export function VoiceReferencePanel({ stage }: { stage: StageInfo }) {
  const {
    runId,
    run,
    refreshRun,
    showToast,
    advanceFromCheckpoint,
    closeActionModal,
    jobRunning,
    partialAutoGPublish,
  } = useApp();
  const [data, setData] = useState<VoiceReferencePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<VoiceReferencePayload>(`/api/runs/${runId}/voice-reference`);
      setData(res);
    } catch (e) {
      showToast(formatApiError(e, "Load voice reference"), "error");
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load, run?.voice_reference_approved]);

  const toggle = async (index: number) => {
    if (!runId || !data?.segments || busy || jobBlocksUi) return;
    const selected = data.segments
      .map((seg, i) => (seg.selected || i === index ? i : -1))
      .filter((i) => i >= 0);
    const next = selected.includes(index)
      ? selected.filter((i) => i !== index)
      : [...selected, index];
    await api(`/api/runs/${runId}/voice-reference/select`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_indices: next }),
    });
    await load();
  };

  const approve = async () => {
    if (!runId || busy || jobBlocksUi) return;
    setBusy(true);
    traceAction("gui.voice_reference.approve", "Approving voice reference", { stage: stage.id });
    try {
      await api(`/api/runs/${runId}/voice-reference/approve`, { method: "POST" });
      showToast("Voice reference approved — choose Chatterbox or record next.");
      const refreshed = await refreshRun();
      closeActionModal();
      if (shouldAdvanceAfterGatePost(refreshed ?? run)) {
        await advanceFromCheckpoint();
      }
    } catch (e) {
      showToast(formatApiError(e, "Approve voice reference"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (data?.approved || run?.voice_reference_approved) {
    return (
      <section className="voice-reference-panel panel-inset" data-testid="voice-reference-panel">
        <p className="hint sm">✓ Interviewer voice reference approved for synthesis.</p>
        <VoiceCloneConsent />
      </section>
    );
  }

  if (!data?.segments?.length) {
    return <p className="hint sm">Confirm gap pickup speaker first — then review voice samples.</p>;
  }

  return (
    <section className="voice-reference-panel panel-inset" data-testid="voice-reference-panel">
      <h4>Voice reference for Chatterbox</h4>
      <p className="hint sm">
        Select clips that sound like the interviewer. Approved audio becomes the clone reference at
        G1.
      </p>
      {data.ref_quality?.warnings?.length ? (
        <p className="hint sm callout warning" data-testid="voice-ref-quality-warn">
          Reference quality: {data.ref_quality.warnings.join(", ")} (avg score{" "}
          {data.ref_quality.avg_clip_score ?? "?"}, {data.ref_quality.duration_sec ?? "?"}s)
        </p>
      ) : data.ref_quality ? (
        <p className="hint sm">
          Reference quality OK — {data.ref_quality.duration_sec ?? "?"}s, score{" "}
          {data.ref_quality.avg_clip_score ?? "?"}
        </p>
      ) : null}
      <ul className="pickup-speaker-list">
        {data.segments.map((seg, i) => {
          const clipUrl =
            runId && seg.clip_path
              ? `/api/runs/${runId}/audio?path=${encodeURIComponent(seg.clip_path)}`
              : null;
          return (
            <li key={i} className={`pickup-speaker-card vo-card${seg.selected ? " selected" : ""}`}>
              <label>
                <input
                  type="checkbox"
                  checked={Boolean(seg.selected)}
                  disabled={busy || jobBlocksUi}
                  onChange={() => void toggle(i)}
                />
                <span className="muted sm">{seg.quote || `Candidate ${i + 1}`}</span>
              </label>
              {clipUrl ? (
                <ArtifactAudio preload="none" src={clipUrl} />
              ) : null}
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        className="btn primary sm"
        data-testid="approve-voice-reference"
        disabled={busy || jobBlocksUi}
        onClick={() => void approve()}
      >
        Approve voice reference
      </button>
    </section>
  );
}
