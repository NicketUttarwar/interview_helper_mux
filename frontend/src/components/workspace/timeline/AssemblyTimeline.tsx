import { useRef, useState } from "react";
import { formatMs } from "../../../utils";
import type { AssemblyChapter, AssemblyClip, AssemblyTimelineData } from "../../../types";

interface Props {
  assembly: AssemblyTimelineData;
  widthPx: number;
  playheadMs: number;
  selectedSegmentId: string | null;
  onSeek: (ms: number) => void;
  onSelectSpeech: (segmentId: string, timelineStartMs: number) => void;
  onReorder?: (dragId: string, targetId: string) => void;
  onJumpToSource?: (segmentId: string) => void;
}

export function AssemblyTimeline({
  assembly,
  widthPx,
  playheadMs,
  selectedSegmentId,
  onSeek,
  onSelectSpeech,
  onReorder,
  onJumpToSource,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [transitionPopover, setTransitionPopover] = useState<{
    text: string;
    duration: number;
    x: number;
    y: number;
  } | null>(null);
  const durationMs = assembly.timeline_duration_ms || 1;
  const clips = assembly.clips || [];

  const msFromEvent = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    const ratio = (clientX - rect.left) / rect.width;
    return Math.max(0, Math.min(durationMs, ratio * durationMs));
  };

  const speechClips = clips.filter((c) => c.type === "speech") as Array<
    Extract<AssemblyClip, { type: "speech" }>
  >;
  const voClips = clips.filter((c) => c.type === "vo_pickup");
  const disfluencyClips = clips.filter((c) => c.type === "disfluency");
  const transitionClips = clips.filter((c) => c.type === "transition");

  const chapterDurations = (assembly.chapters || []).map((ch: AssemblyChapter, i: number) => {
    const start = ch.timeline_start_ms;
    const next = assembly.chapters?.[i + 1]?.timeline_start_ms ?? durationMs;
    const dur = speechClips
      .filter((c) => c.timeline_start_ms >= start && c.timeline_start_ms < next)
      .reduce((n, c) => n + (c.duration_ms || 0), 0);
    return { title: ch.title, duration_ms: dur };
  });

  const renderClip = (clip: AssemblyClip) => {
    const start = clip.timeline_start_ms;
    const dur = clip.duration_ms || 1;
    const left = (start / durationMs) * 100;
    const width = Math.max((dur / durationMs) * 100, 0.5);
    if (clip.type === "speech") {
      const selected = selectedSegmentId === clip.segment_id;
      return (
        <div
          key={`speech-${clip.segment_id}-${start}`}
          className={`assembly-clip speech${selected ? " selected" : ""}`}
          style={{ left: `${left}%`, width: `${width}%` }}
          title={clip.text || clip.segment_id}
          draggable={!!onReorder}
          onDragStart={(e) => e.dataTransfer.setData("text/plain", clip.segment_id)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            onReorder?.(e.dataTransfer.getData("text/plain"), clip.segment_id);
          }}
          onClick={(e) => {
            e.stopPropagation();
            onSelectSpeech(clip.segment_id, start);
          }}
        >
          <span className="seg-label">{clip.segment_id}</span>
        </div>
      );
    }
    if (clip.type === "vo_pickup") {
      return (
        <div
          key={`vo-${clip.line_id}-${start}`}
          className={`assembly-clip vo${clip.recorded_file ? " done" : " missing"}`}
          style={{ left: `${left}%`, width: `${width}%` }}
          title={`${clip.line_id} (${clip.placement})`}
        >
          {clip.line_id}
        </div>
      );
    }
    if (clip.type === "disfluency") {
      return (
        <div
          key={`fill-${clip.event_id}-${start}`}
          className="assembly-clip disfluency"
          style={{ left: `${left}%`, width: `${Math.max(width, 0.4)}%` }}
          title={`${clip.text || "filler"} · ${clip.event_id || ""}`}
        >
          {clip.text || "…"}
        </div>
      );
    }
    if (clip.type === "transition") {
      return (
        <div
          key={`tr-${clip.after_segment_id}-${clip.before_segment_id}-${start}`}
          className="assembly-clip transition"
          style={{ left: `${left}%`, width: `${Math.max(width, 0.3)}%` }}
          title={clip.text || "transition"}
          onClick={(e) => {
            e.stopPropagation();
            setTransitionPopover({
              text: clip.text || "Transition",
              duration: dur,
              x: e.clientX,
              y: e.clientY,
            });
          }}
        >
          ↔
        </div>
      );
    }
    return null;
  };

  const chapters = assembly.chapters || [];

  return (
    <div className="nle-tracks assembly-tracks">
      <p className="muted assembly-hint">
        Assembly timeline · {formatMs(durationMs)} output duration
        {assembly.preview_audio ? " · preview audio" : " · run Apply edits for preview"}
      </p>

      {chapterDurations.length ? (
        <div className="assembly-chapter-durations">
          {chapterDurations.map((ch) => (
            <span key={ch.title} className="chapter-dur-chip">
              {ch.title.slice(0, 20)}: {formatMs(ch.duration_ms)}
            </span>
          ))}
        </div>
      ) : null}

      <div className="track-label">Speech (assembly)</div>
      <div className="timeline-scroll" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
        <div
          ref={trackRef}
          className="timeline-track assembly-lane"
          style={{ width: `${widthPx}px` }}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest(".assembly-clip")) return;
            onSeek(msFromEvent(e.clientX));
          }}
        >
          {speechClips.map((c) => renderClip(c))}
          {disfluencyClips.map((c) => renderClip(c))}
        </div>
        <div className="playhead" style={{ left: `${(playheadMs / durationMs) * 100}%` }} />
      </div>

      <div className="track-label">VO pickup</div>
      <div className="vo-track assembly-lane" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
        {voClips.map((c) => renderClip(c))}
      </div>

      <div className="track-label">Transitions</div>
      <div className="vo-track assembly-lane" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
        {transitionClips.map((c) => renderClip(c))}
      </div>

      {chapters.length ? (
        <>
          <div className="track-label">Chapters</div>
          <div className="chapter-track" style={{ ["--tl-width" as string]: `${widthPx}px` }}>
            {chapters.map((ch: AssemblyChapter) => (
              <div
                key={ch.anchor_segment_id}
                className="chapter-marker assembly-chapter-click"
                style={{ left: `${(ch.timeline_start_ms / durationMs) * 100}%` }}
                title={ch.title}
                onClick={() => onJumpToSource?.(ch.anchor_segment_id)}
              >
                {ch.title.slice(0, 24)}
              </div>
            ))}
          </div>
        </>
      ) : null}

      {transitionPopover ? (
        <>
          <div className="segment-context-backdrop" onClick={() => setTransitionPopover(null)} />
          <div
            className="assembly-transition-popover"
            style={{ left: transitionPopover.x, top: transitionPopover.y }}
          >
            <p>{transitionPopover.text}</p>
            <p className="muted">Duration: {formatMs(transitionPopover.duration)}</p>
          </div>
        </>
      ) : null}
    </div>
  );
}
