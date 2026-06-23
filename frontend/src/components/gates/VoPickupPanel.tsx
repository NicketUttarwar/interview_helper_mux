import { useRef, useState } from "react";
import { useApp } from "../../context/AppContext";
import type { VoLine } from "../../types";

export function VoPickupPanel({ voLines }: { voLines: VoLine[] }) {
  const {
    run,
    runId,
    refreshRun,
    selectStage,
    executeJob,
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

  const lines = voLines.filter((l) => l.delivery === "record");

  const uploadVoFile = async (lineId: string, file: Blob) => {
    if (!runId) return;
    appendClientLog(`Uploading VO for line ${lineId}…`, "action");
    const fd = new FormData();
    fd.append("file", file);
    await fetch(`/api/runs/${runId}/vo/${lineId}`, { method: "POST", body: fd });
    const wasMissing = (run?.g1_missing || []).length > 0;
    await refreshRun();
    if (wasMissing && run?.g1_clear) {
      await selectStage("g1_vo_pickup");
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
        Record or upload pickup lines. Saved to{" "}
        <code>ASSETS/executions/…/vo_pickup/</code>
      </p>
      {lines.map((line) => (
        <div key={line.line_id} className="vo-card">
          <h4>
            {line.line_id} → {line.targets_segment_id}
          </h4>
          <p>{line.text}</p>
          <p className="muted">
            {line.gap_type} ·{" "}
            {line.recorded_file ? `✓ ${line.recorded_file}` : "Missing"}
          </p>
          <div className="vo-actions">
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
          </div>
        </div>
      ))}
      {!(run?.g1_missing || []).length ? (
        <button
          type="button"
          className="btn primary"
          data-testid="vo-continue"
          disabled={jobRunning || actionBusy}
          onClick={() => void executeJob({ mode: "stage", stage: "vo_ingest" })}
        >
          All VO recorded — continue
        </button>
      ) : null}
    </>
  );
}
