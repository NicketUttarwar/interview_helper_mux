import { useCallback, useRef, useState } from "react";
import { formatMs } from "../../../utils";
import { segmentManifestBounds } from "../../../hooks/useTimelineEditor";
import type { TimelineSegment, VoLine, WaveformPeaksData } from "../../../types";

const MIN_TRIM_MS = 300;

interface Props {
  segments: TimelineSegment[];
  voLines: VoLine[];
  durationMs: number;
  widthPx: number;
  zoom: number;
  playheadMs: number;
  selectedSegmentId: string | null;
  waveform: WaveformPeaksData | null;
  chapters?: Array<{ title: string; anchor_segment_id: string; timeline_start_ms?: number }>;
  markers?: Array<Record<string, unknown>>;
  onSeek: (ms: number) => void;
  onSelect: (segId: string, startMs: number) => void;
  onReorder: (dragId: string, targetId: string) => void;
  onTrim: (segId: string, startMs: number, endMs: number, snap: boolean) => void;
}

export function SourceTimeline({
  segments,
  voLines,
  durationMs,
  widthPx,
  playheadMs,
  selectedSegmentId,
  waveform,
  chapters,
  markers,
  onSeek,
  onSelect,
  onReorder,
  onTrim,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [trimPreview, setTrimPreview] = useState<{
    segId: string;
    start: number;
    end: number;
  } | null>(null);

  const msFromEvent = useCallback(
    (clientX: number) => {
      const rect = trackRef.current?.getBoundingClientRect();
      if (!rect) return 0;
      const ratio = (clientX - rect.left) / rect.width;
      return Math.max(0, Math.min(durationMs, ratio * durationMs));
    },
    [durationMs],
  );

  const startTrimDrag = (
    e: React.MouseEvent,
    seg: TimelineSegment,
    edge: "start" | "end",
  ) => {
    e.stopPropagation();
    e.preventDefault();
    const segId = seg.segment_id || "";
    const bounds = segmentManifestBounds(seg);
    const live = { start: seg.start_ms, end: seg.end_ms };

    const onMove = (ev: MouseEvent) => {
      const ms = msFromEvent(ev.clientX);
      if (edge === "start") {
        live.start = Math.max(bounds.start, Math.min(ms, live.end - MIN_TRIM_MS));
      } else {
        live.end = Math.min(bounds.end, Math.max(ms, live.start + MIN_TRIM_MS));
      }
      setTrimPreview({ segId, start: live.start, end: live.end });
    };

    const onUp = (ev: MouseEvent) => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setTrimPreview(null);
      void onTrim(segId, live.start, live.end, ev.shiftKey);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const renderSegment = (seg: TimelineSegment) => {
    const segId = seg.segment_id || seg._nle_label || "";
    const preview = trimPreview?.segId === segId ? trimPreview : null;
    const startMs = preview?.start ?? seg.start_ms;
    const endMs = preview?.end ?? seg.end_ms;
    const bounds = segmentManifestBounds(seg);
    const left = (startMs / durationMs) * 100;
    const width = Math.max(((endMs - startMs) / durationMs) * 100, 0.8);
    const ghostLeft = ((bounds.start - startMs) / durationMs) * 100;
    const ghostRight = ((endMs - bounds.end) / durationMs) * 100;
    const type = seg.type || "";
    const role = seg.speaker_role || "unknown";
    const cls =
      type === "aside"
        ? "aside"
        : role === "interviewer"
          ? "interviewer"
          : "interviewee";

    return (
      <div
        key={segId}
        className={`segment-block ${cls}${seg._mark_redo ? " mark-redo" : ""}${seg._excluded ? " excluded nle-excluded" : ""}${selectedSegmentId === segId ? " selected" : ""}`}
        draggable={!preview}
        data-seg-id={segId}
        style={{ left: `${left}%`, width: `${width}%` }}
        title={seg.text?.slice(0, 120) || segId}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(segId, startMs);
        }}
        onDragStart={(e) => e.dataTransfer.setData("text/plain", segId)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onReorder(e.dataTransfer.getData("text/plain"), segId);
        }}
      >
        {bounds.start < startMs ? (
          <div className="trim-ghost trim-ghost-left" style={{ width: `${Math.abs(ghostLeft)}%` }} />
        ) : null}
        {bounds.end > endMs ? (
          <div className="trim-ghost trim-ghost-right" style={{ width: `${Math.abs(ghostRight)}%` }} />
        ) : null}
        {selectedSegmentId === segId ? (
          <>
            <div
              className="trim-handle trim-handle-left"
              onMouseDown={(e) => startTrimDrag(e, seg, "start")}
              title="Drag to trim start (Shift = snap)"
            />
            <div
              className="trim-handle trim-handle-right"
              onMouseDown={(e) => startTrimDrag(e, seg, "end")}
              title="Drag to trim end (Shift = snap)"
            />
          </>
        ) : null}
        <div className="seg-label">{segId}</div>
        <div>{formatMs(startMs)}</div>
        {preview ? (
          <div className="trim-delta">
            {formatMs(endMs - startMs)}
            {endMs - startMs < seg.end_ms - seg.start_ms ? " (−)" : ""}
          </div>
        ) : null}
      </div>
    );
  };

  const chapterMarkers = (chapters || [])
    .map((ch) => {
      const seg = segments.find((s) => s.segment_id === ch.anchor_segment_id);
      if (!seg) return null;
      return { ...ch, left: (seg.start_ms / durationMs) * 100 };
    })
    .filter(Boolean) as Array<{ title: string; left: number }>;

  return (
    <div className="nle-tracks">
      <div className="track-label">Speech</div>
      <div className="timeline-scroll" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
        <div className="timeline-ruler" style={{ width: `${widthPx}px` }}>
          {Array.from({
            length: Math.floor(durationMs / (durationMs > 600000 ? 60000 : 15000)) + 1,
          }).map((_, i) => {
            const step = durationMs > 600000 ? 60000 : 15000;
            const t = i * step;
            if (t > durationMs) return null;
            return (
              <span key={t} className="ruler-tick" style={{ left: `${(t / durationMs) * 100}%` }}>
                {formatMs(t)}
              </span>
            );
          })}
        </div>
        <div
          ref={trackRef}
          className="timeline-track timeline-track-with-waveform"
          style={{ width: `${widthPx}px` }}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest(".segment-block, .trim-handle")) return;
            onSeek(msFromEvent(e.clientX));
          }}
        >
          {waveform?.peaks?.length ? (
            <svg className="waveform-overlay" viewBox={`0 0 ${widthPx} 120`} preserveAspectRatio="none">
              {waveform.peaks.map((p, i) => {
                const x = (p.t_ms / durationMs) * widthPx;
                const h = p.peak * 100;
                return (
                  <rect
                    key={i}
                    x={x}
                    y={60 - h / 2}
                    width={Math.max(1, widthPx / waveform.peaks.length)}
                    height={h}
                    className="waveform-bar"
                  />
                );
              })}
            </svg>
          ) : null}
          {segments.map(renderSegment)}
        </div>
        <div className="playhead" style={{ left: `${(playheadMs / durationMs) * 100}%` }} />
      </div>

      {chapterMarkers.length ? (
        <>
          <div className="track-label">Chapters</div>
          <div className="chapter-track" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
            {chapterMarkers.map((ch) => (
              <div
                key={ch.title}
                className="chapter-marker"
                style={{ left: `${ch.left}%` }}
                title={ch.title}
              >
                {ch.title.slice(0, 24)}
              </div>
            ))}
          </div>
        </>
      ) : null}

      {(markers || []).length ? (
        <>
          <div className="track-label">Markers</div>
          <div className="marker-track" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
            {(markers || []).map((m, i) => {
              const at = Number(m.at_ms || 0);
              return (
                <div
                  key={i}
                  className="operator-marker"
                  style={{ left: `${(at / durationMs) * 100}%` }}
                  title={String(m.label || m.note || "marker")}
                >
                  ◆
                </div>
              );
            })}
          </div>
        </>
      ) : null}

      <div className="track-label">VO pickup</div>
      <div className="vo-track" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
        {voLines.map((line) => {
          const seg = segments.find((s) => s.segment_id === line.targets_segment_id);
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
  );
}
