import { useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { VoLine } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import { isV2Enabled } from "../../utils/v2Phases";
import { shouldAdvanceAfterGatePost, shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";
import { gateOperatorMustAct, g1AutomationPending } from "../../utils/operatorGates";

type HostedVoFloorSnapshot = {
  status?: string;
  need?: number;
  have?: number;
  resume_producer?: string;
};

function hostedVoFloorFromRun(run: unknown): HostedVoFloorSnapshot | null {
  if (!run || typeof run !== "object") return null;
  const gates = (run as { operator_gates?: Record<string, { hosted_vo_floor?: HostedVoFloorSnapshot }> })
    .operator_gates;
  const fromGate = gates?.g1_vo_pickup?.hosted_vo_floor;
  if (fromGate?.status) return fromGate;
  return null;
}

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
    config,
    partialAutoGPublish,
  } = useApp();
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);
  const recorderRef = useRef<{ media: MediaRecorder | null; chunks: Blob[] }>({
    media: null,
    chunks: [],
  });
  const [recordingLine, setRecordingLine] = useState<string | null>(null);
  const [uploadingLine, setUploadingLine] = useState<string | null>(null);
  const [synthLine, setSynthLine] = useState<string | null>(null);
  const [boundary, setBoundary] = useState<Record<string, { trim_in_ms: number; trim_out_ms: number }>>({});

  const pickupVoice =
    (run as { flow_adaptation?: { pickup_eligible_speaker_id?: string } })?.flow_adaptation
      ?.pickup_eligible_speaker_id ?? null;

  const activeLines = voLines.filter(
    (l) => l.delivery === "record" || l.delivery === "synthesize",
  );
  const v2 = isV2Enabled(config);

  const synthNotice =
    (run as { synthesis_fallback_notice?: string | null })?.synthesis_fallback_notice ||
    null;

  const skipAllOptional = async () => {
    if (!runId || jobBlocksUi || actionBusy) return;
    await api(`/api/runs/${runId}/g1/skip-optional`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    appendClientLog("Skipped optional gap VO — continuing without pickup recordings", "action");
    showToast("Gap VO skipped — continuing without recordings");
    const refreshed = await refreshRun();
    if (shouldAdvanceAfterGatePost(refreshed ?? run)) {
      await advanceFromCheckpoint();
    }
  };

  const suggestTrim = async (lineId: string) => {
    if (!runId) return;
    const data = await api<{ trim_in_ms: number; trim_out_ms: number }>(
      `/api/runs/${runId}/vo/${lineId}/boundary-suggest`,
    );
    setBoundary((b) => ({ ...b, [lineId]: data }));
    showToast(`Suggested trim for ${lineId}`);
  };

  const applyTrim = async (lineId: string) => {
    if (!runId || !boundary[lineId]) return;
    const b = boundary[lineId];
    await api(`/api/runs/${runId}/vo/${lineId}/trim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b),
    });
    appendClientLog(`VO trim applied: ${lineId}`, "action");
  };

  const uploadVoFile = async (lineId: string, file: Blob, mode: "raw" | "match" = "raw") => {
    if (!runId) return;
    setUploadingLine(lineId);
    appendClientLog(
      mode === "match" ? `Voice-matching upload for ${lineId}…` : `Uploading VO for line ${lineId}…`,
      "action",
    );
    try {
      const fd = new FormData();
      fd.append("file", file);
      const path =
        mode === "match"
          ? `/api/runs/${runId}/vo/${lineId}/match`
          : `/api/runs/${runId}/vo/${lineId}`;
      await api(path, { method: "POST", body: fd });
      showToast(mode === "match" ? `Voice matched for ${lineId}.` : `VO saved for ${lineId}.`);
      const wasMissing = (run?.g1_missing || []).length > 0;
      const refreshed = await refreshRun();
      if (wasMissing && refreshed && !(refreshed.g1_missing || []).length) {
        await selectStage("g1_vo_pickup");
      }
    } finally {
      setUploadingLine(null);
    }
  };

  const synthesizeAll = async () => {
    if (!runId) return;
    setSynthLine("__all__");
    try {
      const res = await api<{
        notice?: string;
        fallback?: string;
        synthesized?: string[];
      }>(`/api/runs/${runId}/g1/synthesize-all`, { method: "POST" });
      if (res.fallback === "record" && res.notice) {
        showToast(res.notice, "error");
        appendClientLog(res.notice, "error", "g1_vo_pickup");
      } else {
        showToast("Batch synthesis complete.");
      }
      await refreshRun();
    } catch (e) {
      const msg = formatApiError(e, "Batch VO synthesis failed — pipeline stopped.");
      showToast(msg, "error");
      appendClientLog(msg, "error", "g1_vo_pickup");
    } finally {
      setSynthLine(null);
    }
  };

  const synthesizeLine = async (lineId: string) => {
    if (!runId) return;
    setSynthLine(lineId);
    appendClientLog(`Synthesizing VO for ${lineId}…`, "action", "g1_vo_pickup", "gui.g1.vo.synthesize");
    try {
      const res = await api<{ ok?: boolean; fallback?: string; notice?: string }>(
        `/api/runs/${runId}/vo/${lineId}/synthesize`,
        { method: "POST" },
      );
      if (res.fallback === "record" && res.notice) {
        showToast(res.notice, "error");
        appendClientLog(res.notice, "error", "g1_vo_pickup");
      } else {
        showToast(`Synthesized VO for ${lineId}.`);
      }
      await refreshRun();
    } catch (e) {
      const msg = formatApiError(e, `VO synthesis failed for ${lineId} — pipeline stopped.`);
      showToast(msg, "error");
      appendClientLog(msg, "error", "g1_vo_pickup");
    } finally {
      setSynthLine(null);
    }
  };

  const toneLine = async (lineId: string, tone: string) => {
    if (!runId) return;
    setSynthLine(lineId);
    appendClientLog(`Tone render (${tone}) for ${lineId}…`, "action", "g1_vo_pickup", "gui.g1.vo.tone");
    try {
      await api(`/api/runs/${runId}/vo/${lineId}/tone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tone }),
      });
      showToast(`Re-rendered ${lineId} with ${tone} tone.`);
      await refreshRun();
    } catch {
      showToast("Tone render failed.");
    } finally {
      setSynthLine(null);
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

  const automationPending = g1AutomationPending(run);
  const operatorMustAct = gateOperatorMustAct(run, "g1_vo_pickup");
  const synthOnly =
    activeLines.length > 0 &&
    activeLines.every((l) => l.delivery === "synthesize");
  const hideManualCapture = synthOnly && automationPending && !operatorMustAct;
  const missing = activeLines.filter((l) => !l.recorded_file).length;
  const recorded = activeLines.length - missing;
  const hostedFloor = hostedVoFloorFromRun(run);
  const showHostedFloor =
    hostedFloor &&
    hostedFloor.status &&
    !["UNWARRANTED", "WAIVED", "MET"].includes(hostedFloor.status);

  return (
    <>
      {synthNotice ? (
        <p className="hint sm callout warning" data-testid="synthesis-fallback-notice">
          {synthNotice}
        </p>
      ) : null}
      <p className="gate-progress-subheader hint sm">
        {activeLines.length
          ? `${recorded}/${activeLines.length} pickup line(s) ready`
          : "No pickup lines required."}
      </p>
      {showHostedFloor ? (
        <p className="hint sm" data-testid="g1-hosted-vo-floor-hint">
          Hosted VO floor: {hostedFloor.have ?? "—"}/{hostedFloor.need ?? "—"} ({hostedFloor.status})
          {hostedFloor.resume_producer ? ` — resume ${hostedFloor.resume_producer}` : null}
        </p>
      ) : null}
      {automationPending && !operatorMustAct ? (
        <p className="hint callout info" data-testid="g1-synth-pending">
          Chatterbox is synthesizing gap VO lines in the background — no recording needed.
        </p>
      ) : null}
      <p className="hint">
        {hideManualCapture
          ? "Review synthesized gap lines below."
          : "Record, upload, or synthesize pickup lines as the"}{" "}
        {!hideManualCapture ? (
          <>
            <strong>gap pickup speaker</strong>
            {pickupVoice ? ` (${pickupVoice})` : ""}. Saved to{" "}
            <code>ASSETS/executions/…/vo_pickup/</code>
          </>
        ) : null}
      </p>
      {activeLines.some((l) => l.delivery === "synthesize") && operatorMustAct ? (
        <p className="hint">
          <button
            type="button"
            className="btn sm"
            data-testid="g1-synthesize-all"
            data-action-id="gui.g1.vo.synthesize_all"
            disabled={jobBlocksUi || actionBusy || synthLine !== null}
            onClick={() => void synthesizeAll()}
          >
            Synthesize all (Chatterbox)
          </button>
        </p>
      ) : null}
      {(run?.g1_missing || []).length === 0 && activeLines.some((l) => !l.recorded_file) ? (
        <p className="hint">
          <button
            type="button"
            className="btn ghost sm"
            data-action-id="gui.g1.skip_optional"
            disabled={jobBlocksUi || actionBusy}
            onClick={async () => {
              if (!runId) return;
              await api(`/api/runs/${runId}/g1/skip-optional`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
              });
              appendClientLog("G1 skip-optional", "action", "g1_vo_pickup", "gui.g1.skip_optional");
              await refreshRun();
            }}
          >
            Skip optional (non-blocking) VO
          </button>
        </p>
      ) : null}
      {activeLines.map((line) => {
        const cat = line.line_category || line.gap_type || "";
        const catLabel =
          cat === "episode_preface"
            ? "Preface"
            : cat === "segment_summary"
              ? "Summary"
              : cat === "story_bridge"
                ? "Bridge"
                : cat === "framing_question"
                  ? "Question"
                  : cat === "context_setup"
                    ? "Setup"
                    : cat === "extracted_context"
                      ? "Context"
                      : "";
        return (
        <div key={line.line_id} className="vo-card">
          <h4>
            {line.line_id} → {line.targets_segment_id}
            {catLabel ? (
              <span className="badge sm" style={{ marginLeft: "0.5rem" }}>
                {catLabel}
              </span>
            ) : null}
          </h4>
          <p>{line.text}</p>
          <p className="muted">
            {line.gap_type}
            {line.delivery === "synthesize" ? " · synthesize" : ""}
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
          {hideManualCapture ? (
            <p className="hint sm">
              {line.recorded_file ? `Ready: ${line.recorded_file}` : "Awaiting synthesis…"}
            </p>
          ) : (
          <div className="vo-actions">
            {uploadingLine === line.line_id || synthLine === line.line_id ? (
              <span className="hint sm">
                <span className="spinner-inline" aria-hidden /> Working…
              </span>
            ) : null}
            {line.delivery === "synthesize" ? (
              <button
                type="button"
                className="btn sm"
                data-action-id="gui.g1.vo.synthesize"
                disabled={uploadingLine !== null || synthLine !== null}
                onClick={() => void synthesizeLine(line.line_id)}
              >
                Synthesize
              </button>
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
                disabled={uploadingLine !== null || synthLine !== null}
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
            <input
              type="file"
              accept="audio/*"
              className="vo-upload vo-upload-match"
              title="Upload rough take for voice match"
              data-testid={`vo-match-${line.line_id}`}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void uploadVoFile(line.line_id, file, "match");
              }}
            />
            {line.suggested_tone ? (
              <button
                type="button"
                className="btn sm ghost"
                data-action-id="gui.g1.vo.tone"
                disabled={uploadingLine !== null || synthLine !== null}
                onClick={() => void toneLine(line.line_id, line.suggested_tone || "neutral")}
              >
                Tone: {line.suggested_tone}
              </button>
            ) : null}
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
          )}
        </div>
        );
      })}
      {v2 ? (
        <div className="g1-v2-actions">
          <button
            type="button"
            className="btn ghost"
            data-testid="g1-skip-optional"
            data-action-id="gui.g1.skip_optional"
            disabled={jobBlocksUi || actionBusy}
            onClick={() => void skipAllOptional()}
          >
            Skip — continue without gap VO
          </button>
        </div>
      ) : null}
      {!(run?.g1_missing || []).length ? (
        <button
          type="button"
          className="btn primary"
          data-testid="vo-continue"
          data-action-id="gui.g1.vo.continue"
          disabled={jobBlocksUi || actionBusy}
          onClick={() => void advanceFromCheckpoint()}
        >
          All VO recorded — continue
        </button>
      ) : null}
    </>
  );
}
