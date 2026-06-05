import { useCallback, useRef, useState } from "react";
import { formatMs } from "../../../utils";
import { segmentManifestBounds } from "../../../hooks/useTimelineEditor";
import { SEGMENT_FLAG_LABELS } from "../../../utils/nleHelpers";
import type { TimelineSegment, VoLine, WaveformPeaksData } from "../../../types";
import { SegmentContextMenu } from "./SegmentContextMenu";

const MIN_TRIM_MS = 300;

interface Props {
  segments: TimelineSegment[];
  voLines: VoLine[];
  durationMs: number;
  widthPx: number;
  zoom: number;
  playheadMs: number;
  selectedSegmentId: string | null;
  selectedSegmentIds: string[];
  visibleSegmentIds: Set<string>;
  hideNonMatching: boolean;
  snapEnabled: boolean;
  waveform: WaveformPeaksData | null;
  chapters?: Array<{ title: string; anchor_segment_id: string; timeline_start_ms?: number }>;
  markers?: Array<Record<string, unknown>>;
  scrollRef?: React.RefObject<HTMLDivElement | null>;
  onSeek: (ms: number) => void;
  onSelect: (segId: string, startMs: number, opts?: { additive?: boolean; range?: boolean }) => void;
  onReorder: (dragId: string, targetId: string) => void;
  onTrim: (segId: string, startMs: number, endMs: number, snap: boolean) => void;
  onContextAction: (segId: string, actionId: string) => void;
  onPlayheadDrag?: (ms: number) => void;
  onScroll?: (left: number) => void;
}

export function SourceTimeline({
  segments,
  durationMs,
  widthPx,
  playheadMs,
  selectedSegmentId,
  selectedSegmentIds,
  visibleSegmentIds,
  hideNonMatching,
  snapEnabled,
  waveform,
  chapters,
  markers,
  scrollRef,
  onSeek,
  onSelect,
  onReorder,
  onTrim,
  onContextAction,
  onPlayheadDrag,
  onScroll,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const localScrollRef = useRef<HTMLDivElement>(null);
  const scrollEl = scrollRef || localScrollRef;
  const [trimPreview, setTrimPreview] = useState<{
    segId: string;
    start: number;
    end: number;
  } | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    segId: string;
  } | null>(null);
  const [draggingPlayhead, setDraggingPlayhead] = useState(false);

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
      const snap = snapEnabled || ev.shiftKey;
      void onTrim(segId, live.start, live.end, snap);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const startPlayheadDrag = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDraggingPlayhead(true);
    const onMove = (ev: MouseEvent) => {
      const ms = msFromEvent(ev.clientX);
      onPlayheadDrag?.(ms);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setDraggingPlayhead(false);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const renderSegment = (seg: TimelineSegment) => {
    const segId = seg.segment_id || seg._nle_label || "";
    if (hideNonMatching && !visibleSegmentIds.has(segId)) return null;
    const dimmed = visibleSegmentIds.size < segments.length && !visibleSegmentIds.has(segId);
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
    const multiSelected = selectedSegmentIds.includes(segId);
    const flagHint = (seg.flags || []).map((f) => SEGMENT_FLAG_LABELS[f] || f).join("; ");

    return (
      <div
        key={segId}
        className={`segment-block ${cls}${seg._mark_redo ? " mark-redo" : ""}${seg._excluded ? " excluded nle-excluded" : ""}${selectedSegmentId === segId ? " selected" : ""}${multiSelected ? " multi-selected" : ""}${dimmed ? " dimmed" : ""}${(seg.flags || []).length ? " flagged" : ""}`}
        draggable={!preview}
        data-seg-id={segId}
        style={{ left: `${left}%`, width: `${width}%` }}
        title={[seg.text?.slice(0, 120) || segId, flagHint].filter(Boolean).join(" · ")}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(segId, startMs, {
            additive: e.metaKey || e.ctrlKey,
            range: e.shiftKey,
          });
        }}
        onContextMenu={(e) => {
          e.preventDefault();
          setContextMenu({ x: e.clientX, y: e.clientY, segId });
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
              title="Drag to trim start"
            />
            <div
              className="trim-handle trim-handle-right"
              onMouseDown={(e) => startTrimDrag(e, seg, "end")}
              title="Drag to trim end"
            />
          </>
        ) : null}
        <div className="seg-label">{segId}</div>
        {(seg.flags || []).length ? <span className="seg-flag-dot" title={flagHint}>⚑</span> : null}
        <div>{formatMs(startMs)}</div>
        {preview ? (
          <div className="trim-delta-tooltip">
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
      <div
        className="timeline-scroll"
        ref={scrollEl}
        style={{ ["--tl-width" as string]: `${widthPx}px` }}
        onScroll={() => onScroll?.(scrollEl.current?.scrollLeft ?? 0)}
      >
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
            if ((e.target as HTMLElement).closest(".segment-block, .trim-handle, .playhead-handle")) return;
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
        <div
          className={`playhead${draggingPlayhead ? " dragging" : ""}`}
          style={{ left: `${(playheadMs / durationMs) * 100}%` }}
        >
          <div className="playhead-handle" onMouseDown={startPlayheadDrag} title="Drag playhead" />
        </div>
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

      {contextMenu ? (
        <SegmentContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          segmentId={contextMenu.segId}
          onAction={(action) => onContextAction(contextMenu.segId, action)}
          onClose={() => setContextMenu(null)}
        />
      ) : null}
    </div>
  );
}
