import type { TimelineMode, TimelineSegment } from "../../../types";
import type { DirtyReason } from "../../../hooks/useTimelineEditor";

interface Props {
  mode: TimelineMode;
  zoom: number;
  dirtyReason: DirtyReason;
  segments: TimelineSegment[];
  selectedSegmentId: string | null;
  snapEnabled: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onModeChange: (mode: TimelineMode) => void;
  onZoomChange: (zoom: number) => void;
  onSnapChange: (snap: boolean) => void;
  onFitSelection: () => void;
  onSplit: () => void;
  onExclude: () => void;
  onMarkRedo: () => void;
  onTrimAsides: () => void;
  onTightenPauses: () => void;
  onRippleDelete: () => void;
  onRestore: () => void;
  onSnapTrim: () => void;
  onAddMarker: () => void;
  onOpenReview: () => void;
  onUndo: () => void;
  onRedo: () => void;
}

function ToolbarGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="timeline-toolbar-group">
      <span className="timeline-toolbar-label">{label}</span>
      <div className="timeline-toolbar-buttons">{children}</div>
    </div>
  );
}

export function TimelineToolbar({
  mode,
  zoom,
  dirtyReason,
  segments,
  selectedSegmentId,
  snapEnabled,
  canUndo,
  canRedo,
  onModeChange,
  onZoomChange,
  onSnapChange,
  onFitSelection,
  onSplit,
  onExclude,
  onMarkRedo,
  onTrimAsides,
  onTightenPauses,
  onRippleDelete,
  onRestore,
  onSnapTrim,
  onAddMarker,
  onOpenReview,
  onUndo,
  onRedo,
}: Props) {
  const asideCount = segments.filter((s) => s.type === "aside" && !s._excluded).length;

  return (
    <div className="nle-toolbar timeline-toolbar">
      <ToolbarGroup label="View">
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
        <label className="timeline-snap-toggle">
          <input
            type="checkbox"
            checked={snapEnabled}
            onChange={(e) => onSnapChange(e.target.checked)}
          />
          Snap
        </label>
        <button
          type="button"
          className="btn sm ghost"
          disabled={!selectedSegmentId}
          onClick={() => void onFitSelection()}
        >
          Fit selection
        </button>
      </ToolbarGroup>

      <ToolbarGroup label="Edit">
        <button type="button" className="btn sm ghost" onClick={() => void onSplit()}>
          Split
        </button>
        <button
          type="button"
          className="btn sm ghost"
          onClick={() => void onSnapTrim()}
          disabled={!selectedSegmentId}
        >
          Snap trim
        </button>
        <button
          type="button"
          className="btn sm ghost"
          onClick={() => void onTightenPauses()}
          disabled={!selectedSegmentId}
        >
          Tighten pauses
        </button>
      </ToolbarGroup>

      <ToolbarGroup label="Structure">
        <button type="button" className="btn sm ghost" onClick={() => void onExclude()}>
          Exclude
        </button>
        <button type="button" className="btn sm ghost" onClick={() => void onMarkRedo()}>
          Mark redo
        </button>
        <button
          type="button"
          className="btn sm ghost"
          onClick={() => void onRippleDelete()}
          disabled={!selectedSegmentId}
        >
          Ripple delete
        </button>
        <button
          type="button"
          className="btn sm ghost"
          onClick={() => void onRestore()}
          disabled={!selectedSegmentId}
        >
          Restore
        </button>
        {asideCount > 0 ? (
          <button type="button" className="btn sm ghost" onClick={() => void onTrimAsides()}>
            Exclude asides ({asideCount})
          </button>
        ) : null}
      </ToolbarGroup>

      <ToolbarGroup label="Review">
        <button type="button" className="btn sm ghost" onClick={onOpenReview}>
          Review queue
        </button>
        <button type="button" className="btn sm ghost" disabled={!canUndo} onClick={() => void onUndo()}>
          Undo
        </button>
        <button type="button" className="btn sm ghost" disabled={!canRedo} onClick={() => void onRedo()}>
          Redo
        </button>
      </ToolbarGroup>

      <ToolbarGroup label="Markers">
        <button type="button" className="btn sm ghost" onClick={() => void onAddMarker()}>
          Add marker
        </button>
      </ToolbarGroup>

      {dirtyReason ? (
        <span className="dirty-badge timeline-dirty-banner">Unapplied {dirtyReason} edits</span>
      ) : null}
    </div>
  );
}
