import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs, nleHasOperatorEdits } from "../../utils";
import type { TimelineSegment } from "../../types";

export function NlePanel() {
  const { runId, timeline, refreshRun, executeJob } = useApp();
  const [zoom, setZoom] = useState(1);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const playerRef = useRef<HTMLAudioElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const nle = timeline?.nle || null;
  const segments = timeline?.segments || [];
  const durationMs = timeline?.duration_ms || 1;

  useEffect(() => {
    if (nle?.zoom) setZoom(nle.zoom);
  }, [nle?.zoom]);

  const seekTo = useCallback((ms: number) => {
    setPlayheadMs(ms);
    if (playerRef.current) playerRef.current.currentTime = ms / 1000;
  }, []);

  const selectSegment = useCallback(
    (segId: string, startMs: number) => {
      setSelectedSegmentId(segId);
      seekTo(startMs);
    },
    [seekTo],
  );

  const patchSelectedSegment = async (patch: Record<string, unknown>) => {
    if (!selectedSegmentId || !runId) {
      return;
    }
    await api(`/api/runs/${runId}/nle/segment`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_id: selectedSegmentId, patch }),
    });
    await refreshRun();
  };

  const splitAtPlayhead = async () => {
    if (!selectedSegmentId || !runId) return;
    await api(`/api/runs/${runId}/nle/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        segment_id: selectedSegmentId,
        at_ms: Math.round(playheadMs),
      }),
    });
    await refreshRun();
  };

  const saveNle = async (showMsg = true) => {
    if (!runId) return;
    const data = {
      ...(nle || {}),
      playhead_ms: Math.round(playheadMs),
      zoom,
    };
    await api(`/api/runs/${runId}/nle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data }),
    });
    if (showMsg) {
      /* toast handled by caller if needed */
    }
  };

  const reorderSegment = async (dragId: string, targetId: string) => {
    if (!dragId || dragId === targetId || !runId) return;
    const order = nle?.sequence_order?.length
      ? [...nle.sequence_order]
      : segments.map((s) => s.segment_id || s._nle_label || "");
    const from = order.indexOf(dragId);
    const to = order.indexOf(targetId);
    if (from < 0 || to < 0) return;
    order.splice(from, 1);
    order.splice(to, 0, dragId);
    await api(`/api/runs/${runId}/nle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data: { ...(nle || {}), sequence_order: order, playhead_ms: playheadMs, zoom },
      }),
    });
    await refreshRun();
  };

  const audioPath = timeline?.normalized_audio
    ? `/api/runs/${runId}/audio?path=${encodeURIComponent(timeline.normalized_audio)}`
    : `/api/runs/${runId}/source-audio`;

  const widthPx = Math.max(800, durationMs / 50) * zoom;
  const overrides = nle?.segment_overrides || {};

  const renderSegment = (seg: TimelineSegment) => {
    const segId = seg.segment_id || seg._nle_label || "";
    const left = (seg.start_ms / durationMs) * 100;
    const width = Math.max(((seg.end_ms - seg.start_ms) / durationMs) * 100, 0.8);
    const type = seg.type || "";
    const role = seg.speaker_role || "unknown";
    const cls =
      type === "aside"
        ? "aside"
        : role === "interviewer"
          ? "interviewer"
          : "interviewee";
    const ov = (overrides[segId] || {}) as Record<string, unknown>;
    const splitHint = Array.isArray(ov.split_into)
      ? ` · split → ${(ov.split_into as string[]).join(", ")}`
      : "";
    const trimHint =
      ov.start_ms != null && ov.end_ms != null
        ? ` · trim ${formatMs(ov.start_ms as number)}–${formatMs(ov.end_ms as number)}`
        : "";

    return (
      <div
        key={segId}
        className={`segment-block ${cls}${seg._mark_redo ? " mark-redo" : ""}${seg._excluded ? " excluded nle-excluded" : ""}${selectedSegmentId === segId ? " selected" : ""}`}
        draggable
        data-seg-id={segId}
        style={{ left: `${left}%`, width: `${width}%` }}
        title={`${seg.text?.slice(0, 120) || segId}${splitHint}${trimHint}`}
        onClick={(e) => {
          e.stopPropagation();
          selectSegment(segId, seg.start_ms);
        }}
        onDragStart={(e) => e.dataTransfer.setData("text/plain", segId)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void reorderSegment(e.dataTransfer.getData("text/plain"), segId);
        }}
      >
        <div className="seg-label">{segId}</div>
        <div>{formatMs(seg.start_ms)}</div>
      </div>
    );
  };

  return (
    <div className="panel nle-panel">
      <div className="panel-head">
        <h3>Non-linear editor</h3>
        <div className="nle-toolbar">
          <label className="zoom-label">
            Zoom{" "}
            <input
              type="range"
              min={1}
              max={8}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            />
          </label>
          <button type="button" className="btn sm ghost" onClick={() => void splitAtPlayhead()}>
            Split at playhead
          </button>
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => void patchSelectedSegment({ mark_redo: true })}
          >
            Mark redo
          </button>
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => void patchSelectedSegment({ excluded: true })}
          >
            Exclude segment
          </button>
          <button type="button" className="btn sm primary" onClick={() => void saveNle()}>
            Save timeline
          </button>
        </div>
      </div>

      {!segments.length ? (
        <p className="empty-state">
          NLE timeline appears after segment classification.
        </p>
      ) : (
        <>
          <p className="muted">
            {segments.length} segments · {formatMs(durationMs)} · zoom {zoom}x
          </p>
          {nleHasOperatorEdits(nle as Record<string, unknown> | null) ? (
            <div className="nle-rerun-banner">
              <p>Timeline edits detected — re-run ranking or rebuild EDL to apply.</p>
              <div className="btn-row">
                <button
                  type="button"
                  className="btn sm primary"
                  onClick={() =>
                    void executeJob({ mode: "stage", stage: "full_master_ranking" })
                  }
                >
                  Re-run ranking
                </button>
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={() => void executeJob({ mode: "stage", stage: "edl_flow1" })}
                >
                  Rebuild EDL
                </button>
              </div>
            </div>
          ) : null}
          <div className="nle-tracks">
            <div className="track-label">Speech</div>
            <div
              className="timeline-scroll"
              style={{ ["--tl-width" as string]: `${widthPx}px` }}
            >
              <div
                className="timeline-ruler"
                style={{ width: `${widthPx}px` }}
              >
                {Array.from({
                  length: Math.floor(durationMs / (durationMs > 600000 ? 60000 : 15000)) + 1,
                }).map((_, i) => {
                  const step = durationMs > 600000 ? 60000 : 15000;
                  const t = i * step;
                  if (t > durationMs) return null;
                  return (
                    <span
                      key={t}
                      className="ruler-tick"
                      style={{ left: `${(t / durationMs) * 100}%` }}
                    >
                      {formatMs(t)}
                    </span>
                  );
                })}
              </div>
              <div
                ref={trackRef}
                className="timeline-track"
                style={{ width: `${widthPx}px` }}
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest(".segment-block")) return;
                  const rect = trackRef.current?.getBoundingClientRect();
                  if (!rect) return;
                  const ratio = (e.clientX - rect.left) / rect.width;
                  seekTo(ratio * durationMs);
                }}
              >
                {segments.map(renderSegment)}
              </div>
              <div
                className="playhead"
                style={{ left: `${(playheadMs / durationMs) * 100}%` }}
              />
            </div>
            <div className="track-label">VO pickup</div>
            <div className="vo-track" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
              {(timeline?.vo_lines || []).map((line) => {
                const seg = segments.find(
                  (s) => s.segment_id === line.targets_segment_id,
                );
                if (!seg) return null;
                return (
                  <div
                    key={line.line_id}
                    className={`vo-chip${line.recorded_file ? " done" : " missing"}`}
                    style={{ left: `${(seg.start_ms / durationMs) * 100}%` }}
                    title={line.text}
                  >
                    {line.line_id}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      <audio
        ref={playerRef}
        controls
        className="audio-player"
        src={segments.length ? audioPath : undefined}
        onTimeUpdate={() => {
          if (playerRef.current)
            setPlayheadMs(playerRef.current.currentTime * 1000);
        }}
      />
    </div>
  );
}
