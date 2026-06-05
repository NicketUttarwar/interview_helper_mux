import { useRef } from "react";

interface Props {
  durationMs: number;
  widthPx: number;
  scrollLeftPx: number;
  viewportWidthPx: number;
  segmentSpans: Array<{ id: string; start: number; end: number; excluded?: boolean }>;
  onScrollTo: (scrollLeft: number) => void;
}

export function TimelineMiniMap({
  durationMs,
  widthPx,
  scrollLeftPx,
  viewportWidthPx,
  segmentSpans,
  onScrollTo,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  if (durationMs < 30 * 60 * 1000) return null;

  const mapWidth = Math.min(600, widthPx);
  const ratio = mapWidth / widthPx;
  const viewLeft = scrollLeftPx * ratio;
  const viewWidth = Math.max(20, viewportWidthPx * ratio);

  const msFromEvent = (clientX: number) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return 0;
    const r = (clientX - rect.left) / rect.width;
    return r * widthPx - viewportWidthPx / 2;
  };

  return (
    <div
      ref={ref}
      className="timeline-minimap"
      style={{ width: `${mapWidth}px` }}
      onClick={(e) => onScrollTo(Math.max(0, msFromEvent(e.clientX)))}
    >
      {segmentSpans.map((s) => (
        <div
          key={s.id}
          className={`minimap-seg${s.excluded ? " excluded" : ""}`}
          style={{
            left: `${(s.start / durationMs) * 100}%`,
            width: `${Math.max(0.2, ((s.end - s.start) / durationMs) * 100)}%`,
          }}
        />
      ))}
      <div
        className="minimap-viewport"
        style={{ left: `${viewLeft}px`, width: `${viewWidth}px` }}
      />
    </div>
  );
}
