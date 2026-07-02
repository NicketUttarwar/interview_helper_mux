import { useRef, useState } from "react";
import { useApp } from "../../context/AppContext";
import type { VoLine } from "../../types";

export function VoPickupPanel({ voLines }: { voLines: VoLine[] }) {
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
  const [boundary, setBoundary] = useState<Record<string, { trim_in_ms: number; trim_out_ms: number }>>({});

  const pickupVoice =
    (run as { flow_adaptation?: { pickup_eligible_speaker_id?: string } })?.flow_adaptation
      ?.pickup_eligible_speaker_id ?? null;

  const lines = voLines.filter((l) => l.delivery === "record");

  const suggestTrim = async (lineId: string) => {
    if (!runId) return;
    const res = await fetch(`/api/runs/${runId}/vo/${lineId}/boundary-suggest`);
    if (!res.ok) return;
    const data = (await res.json()) as { trim_in_ms: number; trim_out_ms: number };
    setBoundary((b) => ({ ...b, [lineId]: data }));
    showToast(`Suggested trim for ${lineId}`);
  };

  const applyTrim = async (lineId: string) => {
    if (!runId || !boundary[lineId]) return;
    const b = boundary[lineId];
    await fetch(`/api/runs/${runId}/vo/${lineId}/trim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b),
    });
    showToast(`Trim applied for ${lineId}`);
    appendClientLog(`VO trim applied: ${lineId}`, "action");
  };

  const uploadVoFile = async (lineId: string, file: Blob) => {
    if (!runId) return;
    setUploadingLine(lineId);
    showToast(`Uploading VO for ${lineId}…`);
    appendClientLog(`Uploading VO for line ${lineId}…`, "action");
    try {
      const fd = new FormData();
      fd.append("file", file);
      await fetch(`/api/runs/${runId}/vo/${lineId}`, { method: "POST", body: fd });
      showToast(`VO saved for ${lineId}.`);
      const wasMissing = (run?.g1_missing || []).length > 0;
      const refreshed = await refreshRun();
      if (wasMissing && refreshed && !(refreshed.g1_missing || []).length) {
        await selectStage("g1_vo_pickup");
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
        await uploadVoFile(
          lineId,
          new Blob(recorderRef.current.chunks, { type: "audio/webm" }),
        );
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

  const missing = lines.filter((l) => !l.recorded_file).length;
  const recorded = lines.length - missing;

  return (
    <>
      <p className="gate-progress-subheader hint sm">
        {lines.length
          ? `${recorded}/${lines.length} pickup line(s) recorded`
          : "No pickup lines required."}
      </p>
      <p className="hint">
        Record or upload pickup lines as the <strong>gap pickup speaker</strong>
        {pickupVoice ? ` (${pickupVoice})` : ""}. Saved to{" "}
        <code>ASSETS/executions/…/vo_pickup/</code>
      </p>
      {lines.map((line) => (
        <div key={line.line_id} className="vo-card">
          <h4>
            {line.line_id} → {line.targets_segment_id}
          </h4>
          <p>{line.text}</p>
          <p className="muted">
            {line.gap_type}
            {line.post_preview ? " · post-preview" : ""}
            {line.voice_speaker_id ? ` · voice: ${line.voice_speaker_id}` : ""} ·{" "}
            {line.recorded_file ? `✓ ${line.recorded_file}` : "Missing"}
          </p>
          {boundary[line.line_id] ? (
            <p className="hint sm">
              Trim suggest: {boundary[line.line_id].trim_in_ms}–
              {boundary[line.line_id].trim_out_ms} ms
            </p>
          ) : null}
          <div className="vo-actions">
            {uploadingLine === line.line_id ? (
              <span className="hint sm">
                <span className="spinner-inline" aria-hidden /> Uploading…
              </span>
            ) : null}
            {recordingLine === line.line_id ? (
              <button
                type="button"
                className="btn sm ghost"
                onClick={stopRecording}
              >
                Stop
              </button>
            ) : (
              <button
                type="button"
                className="btn sm btn-record"
                disabled={uploadingLine !== null}
                onClick={() => void startRecording(line.line_id)}
              >
                Record
              </button>
            )}
            <input
              type="file"
              accept="audio/*"
              className="vo-upload"
              data-testid={`vo-upload-${line.line_id}`}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void uploadVoFile(line.line_id, file);
              }}
            />
            {line.recorded_file ? (
              <>
                <button
                  type="button"
                  className="btn sm ghost"
                  disabled={uploadingLine !== null}
                  onClick={() => void suggestTrim(line.line_id)}
                >
                  Suggest trim
                </button>
                {boundary[line.line_id] ? (
                  <button
                    type="button"
                    className="btn sm"
                    onClick={() => void applyTrim(line.line_id)}
                  >
                    Apply trim
                  </button>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      ))}
      {!(run?.g1_missing || []).length ? (
        <button
          type="button"
          className="btn primary"
          data-testid="vo-continue"
          disabled={jobRunning || actionBusy}
          onClick={() => void advanceFromCheckpoint()}
        >
          All VO recorded — continue
        </button>
      ) : null}
    </>
  );
}
