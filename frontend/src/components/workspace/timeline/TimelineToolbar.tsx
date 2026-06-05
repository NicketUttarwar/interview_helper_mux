import type { TimelineMode, TimelineSegment } from "../../../types";
import type { DirtyReason } from "../../../hooks/useTimelineEditor";

interface Props {
  mode: TimelineMode;
  zoom: number;
  dirtyReason: DirtyReason;
  segments: TimelineSegment[];
  selectedSegmentId: string | null;
  onModeChange: (mode: TimelineMode) => void;
  onZoomChange: (zoom: number) => void;
  onSplit: () => void;
  onExclude: () => void;
  onMarkRedo: () => void;
  onTrimAsides: () => void;
  onTightenPauses: () => void;
  onRippleDelete: () => void;
  onRestore: () => void;
  onSnapTrim: () => void;
  onAddMarker: () => void;
}

export function TimelineToolbar({
  mode,
  zoom,
  dirtyReason,
  segments,
  selectedSegmentId,
  onModeChange,
  onZoomChange,
  onSplit,
  onExclude,
  onMarkRedo,
  onTrimAsides,
  onTightenPauses,
  onRippleDelete,
  onRestore,
  onSnapTrim,
  onAddMarker,
}: Props) {
  const asideCount = segments.filter((s) => s.type === "aside" && !s._excluded).length;

  return (
    <div className="nle-toolbar timeline-toolbar">
      <div className="timeline-mode-toggle">
        <button
          type="button"
          className={`btn sm${mode === "source" ? " primary" : " ghost"}`}
          onClick={() => onModeChange("source")}
        >
          Source
        </button>
        <button
          type="button"
          className={`btn sm${mode === "assembly" ? " primary" : " ghost"}`}
          onClick={() => onModeChange("assembly")}
        >
          Assembly
        </button>
      </div>
      <label className="zoom-label">
        Zoom{" "}
        <input
          type="range"
          min={1}
          max={8}
          value={zoom}
          onChange={(e) => onZoomChange(Number(e.target.value))}
        />
      </label>
      <button type="button" className="btn sm ghost" onClick={() => void onSplit()}>
        Split at playhead
      </button>
      <button type="button" className="btn sm ghost" onClick={() => void onExclude()}>
        Exclude
      </button>
      <button type="button" className="btn sm ghost" onClick={() => void onMarkRedo()}>
        Mark redo
      </button>
      <button type="button" className="btn sm ghost" onClick={() => void onSnapTrim()} disabled={!selectedSegmentId}>
        Snap trim
      </button>
      <button type="button" className="btn sm ghost" onClick={() => void onTightenPauses()} disabled={!selectedSegmentId}>
        Tighten pauses
      </button>
      <button type="button" className="btn sm ghost" onClick={() => void onRippleDelete()} disabled={!selectedSegmentId}>
        Ripple delete
      </button>
      <button type="button" className="btn sm ghost" onClick={() => void onRestore()} disabled={!selectedSegmentId}>
        Restore
      </button>
      {asideCount > 0 ? (
        <button type="button" className="btn sm ghost" onClick={() => void onTrimAsides()}>
          Exclude asides ({asideCount})
        </button>
      ) : null}
      <button type="button" className="btn sm ghost" onClick={() => void onAddMarker()}>
        Add marker
      </button>
      {dirtyReason ? (
        <span className="dirty-badge muted">Unapplied {dirtyReason} edits</span>
      ) : null}
    </div>
  );
}
