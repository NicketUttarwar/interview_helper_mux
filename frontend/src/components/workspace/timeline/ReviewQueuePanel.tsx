import type { TimelineSegment } from "../../../types";
import type { ReviewFilter } from "../../../utils/nleHelpers";
import { formatMs } from "../../../utils";

interface Props {
  open: boolean;
  filter: ReviewFilter;
  queue: TimelineSegment[];
  index: number;
  onClose: () => void;
  onFilterChange: (f: ReviewFilter) => void;
  onPrev: () => void;
  onNext: () => void;
  onExclude: () => void;
  onRestore: () => void;
  onSnapTrim: () => void;
  onTighten: () => void;
  onMarkRedo: () => void;
  onSkip: () => void;
}

const FILTER_CHIPS: { id: ReviewFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "flagged", label: "Flagged" },
  { id: "aside", label: "Asides" },
  { id: "redo", label: "Redo" },
  { id: "low_confidence", label: "Low conf." },
  { id: "off_selection", label: "Off selection" },
  { id: "qc_issue", label: "QC" },
];

export function ReviewQueuePanel({
  open,
  filter,
  queue,
  index,
  onClose,
  onFilterChange,
  onPrev,
  onNext,
  onExclude,
  onRestore,
  onSnapTrim,
  onTighten,
  onMarkRedo,
  onSkip,
}: Props) {
  if (!open) return null;
  const seg = queue[index];

  return (
    <div className="review-queue-panel">
      <div className="review-queue-head">
        <strong>Review queue</strong>
        <button type="button" className="btn sm ghost" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="review-queue-chips">
        {FILTER_CHIPS.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`btn sm${filter === c.id ? " primary" : " ghost"}`}
            onClick={() => onFilterChange(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>
      {!queue.length ? (
        <p className="muted">No segments match this filter.</p>
      ) : (
        <>
          <p className="review-queue-progress">
            {index + 1} of {queue.length}
            {seg?.segment_id ? ` · ${seg.segment_id}` : ""}
          </p>
          {seg ? (
            <p className="review-queue-text">{seg.text?.slice(0, 200) || "(no text)"}</p>
          ) : null}
          {seg ? (
            <p className="muted">
              {formatMs(seg.start_ms)} – {formatMs(seg.end_ms)} · {seg.type || "—"}
            </p>
          ) : null}
          <div className="btn-row review-queue-actions">
            <button type="button" className="btn sm ghost" disabled={index <= 0} onClick={onPrev}>
              Previous
            </button>
            <button
              type="button"
              className="btn sm ghost"
              disabled={index >= queue.length - 1}
              onClick={onNext}
            >
              Next
            </button>
            <button type="button" className="btn sm ghost" onClick={() => void onExclude()}>
              Exclude
            </button>
            <button type="button" className="btn sm ghost" onClick={() => void onRestore()}>
              Restore
            </button>
            <button type="button" className="btn sm ghost" onClick={() => void onSnapTrim()}>
              Snap trim
            </button>
            <button type="button" className="btn sm ghost" onClick={() => void onTighten()}>
              Tighten
            </button>
            <button type="button" className="btn sm ghost" onClick={() => void onMarkRedo()}>
              Mark redo
            </button>
            <button type="button" className="btn sm ghost" onClick={onSkip}>
              Skip
            </button>
          </div>
        </>
      )}
    </div>
  );
}
