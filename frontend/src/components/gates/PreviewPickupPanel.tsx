import { useMemo, useRef, useState } from "react";
import { useApp } from "../../context/AppContext";
import type { VoLine } from "../../types";
import { traceAction } from "../../operator/traceAction";

/** G1.5 — re-record pickup lines after assembly preview listen (TBIY). */
export function PreviewPickupPanel({ voLines }: { voLines: VoLine[] }) {
  const {
    run,
    runId,
    refreshRun,
    selectStage,
    advanceFromCheckpoint,
    showToast,
    appendClientLog,
    jobRunning,
    actionBusy,
  } = useApp();
  const recorderRef = useRef<{ media: MediaRecorder | null; chunks: Blob[] }>({
    media: null,
    chunks: [],
  });
  const [recordingLine, setRecordingLine] = useState<string | null>(null);
  const [uploadingLine, setUploadingLine] = useState<string | null>(null);

  const lines = useMemo(
    () =>
      voLines.filter(
        (l) =>
          l.delivery === "record" &&
          l.post_preview &&
          !l.post_preview_satisfied,
      ),
    [voLines],
  );

  const pickupVoice =
    (run as { flow_adaptation?: { pickup_eligible_speaker_id?: string } })?.flow_adaptation
      ?.pickup_eligible_speaker_id ?? null;

  const uploadVoFile = async (lineId: string, file: Blob) => {
    if (!runId) return;
    setUploadingLine(lineId);
    traceAction("gui.g1_5.vo.upload", `Uploading post-preview VO for ${lineId}`, {
      stage: "g1_5_preview_pickup",
    });
    showToast(`Uploading post-preview VO for ${lineId}…`);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await fetch(`/api/runs/${runId}/vo/${lineId}`, { method: "POST", body: fd });
      showToast(`Post-preview VO saved for ${lineId}.`);
      appendClientLog(`G1.5 VO saved: ${lineId}`, "action");
      const wasPending = (run?.g1_5_preview_pickup_pending || []).length > 0;
      const refreshed = await refreshRun();
      if (wasPending && refreshed && !(refreshed.g1_5_preview_pickup_pending || []).length) {
        await selectStage("g1_5_preview_pickup");
      }
    } finally {
      setUploadingLine(null);
    }
  };

  const startRecording = async (lineId: string) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const media = new MediaRecorder(stream);
      recorderRef.current = { media, chunks: [] };
      media.ondataavailable = (e) => recorderRef.current.chunks.push(e.data);
      media.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        await uploadVoFile(lineId, new Blob(recorderRef.current.chunks, { type: "audio/webm" }));
        setRecordingLine(null);
      };
      media.start();
      setRecordingLine(lineId);
    } catch {
      showToast("Microphone access denied or unavailable.");
    }
  };

  const stopRecording = () => {
    if (recorderRef.current.media?.state === "recording") {
      recorderRef.current.media.stop();
    }
  };

  const pendingCount = run?.g1_5_preview_pickup_pending?.length ?? lines.length;
  const allClear = pendingCount === 0;

  return (
    <>
      <p className="gate-progress-subheader hint sm">
        {allClear
          ? "All post-preview pickup lines re-recorded."
          : `${pendingCount} post-preview line(s) need re-recording after preview listen.`}
      </p>
      <p className="hint">
        You heard the assembly preview — re-record reaction lines as{" "}
        <strong>gap pickup speaker</strong>
        {pickupVoice ? ` (${pickupVoice})` : ""}. Pre-preview takes do not count.
      </p>
      {lines.map((line) => (
        <div key={line.line_id} className="vo-card g1-5-card">
          <h4>
            {line.line_id} → {line.targets_segment_id}
          </h4>
          <p>{line.text}</p>
          <p className="muted">
            {line.gap_type} · post-preview ·{" "}
            {line.post_preview_satisfied ? "✓ re-recorded" : "Needs re-record"}
          </p>
          <div className="vo-actions">
            {uploadingLine === line.line_id ? (
              <span className="hint sm">
                <span className="spinner-inline" aria-hidden /> Uploading…
              </span>
            ) : null}
            {recordingLine === line.line_id ? (
              <button type="button" className="btn sm ghost" onClick={stopRecording}>
                Stop
              </button>
            ) : (
              <button
                type="button"
                className="btn sm btn-record"
                disabled={uploadingLine !== null}
                onClick={() => void startRecording(line.line_id)}
              >
                Re-record
              </button>
            )}
            <input
              type="file"
              accept="audio/*"
              className="vo-upload"
              data-testid={`g1-5-vo-upload-${line.line_id}`}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void uploadVoFile(line.line_id, file);
              }}
            />
          </div>
        </div>
      ))}
      {allClear ? (
        <button
          type="button"
          className="btn primary"
          data-testid="g1-5-preview-continue"
          disabled={jobRunning || actionBusy}
          onClick={() => void advanceFromCheckpoint()}
        >
          Post-preview lines done — continue to SFX
        </button>
      ) : null}
    </>
  );
}
