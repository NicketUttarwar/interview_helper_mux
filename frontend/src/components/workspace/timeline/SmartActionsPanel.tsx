import { useMemo, useState } from "react";
import type { TimelineSegment } from "../../../types";
import { estimateTrimRemovedMs, segmentHasFlags } from "../../../utils/nleHelpers";

interface Props {
  segments: TimelineSegment[];
  selectionOrder: string[];
  lowConfSegmentIds: Set<string>;
  onExcludeAsides: () => void;
  onTightenAll: (ids: string[]) => void;
  onExcludeOffSelection: (ids: string[]) => void;
  onOpenReview: (filter: "flagged" | "redo" | "low_confidence" | "off_selection") => void;
  onSilenceTrim: (ids: string[]) => void;
  selectedSegmentIds: string[];
}

export function SmartActionsPanel({
  segments,
  selectionOrder,
  lowConfSegmentIds,
  onExcludeAsides,
  onTightenAll,
  onExcludeOffSelection,
  onOpenReview,
  onSilenceTrim,
  selectedSegmentIds,
}: Props) {
  const [confirm, setConfirm] = useState<string | null>(null);

  const asideSegs = useMemo(
    () => segments.filter((s) => s.type === "aside" && !s._excluded),
    [segments],
  );
  const flaggedSegs = useMemo(
    () => segments.filter((s) => segmentHasFlags(s) && !s._excluded),
    [segments],
  );
  const redoSegs = useMemo(() => segments.filter((s) => s._mark_redo), [segments]);
  const offSelSegs = useMemo(
    () =>
      segments.filter((s) => {
        const id = s.segment_id || "";
        return id && !selectionOrder.includes(id) && !s._excluded;
      }),
    [segments, selectionOrder],
  );
  const tightenTargets = useMemo(
    () => segments.filter((s) => !s._excluded).map((s) => s.segment_id!).filter(Boolean),
    [segments],
  );
  const estAsideMs = asideSegs.reduce((n, s) => n + (s.end_ms - s.start_ms), 0);
  const estTightenMs = tightenTargets.reduce((n, id) => {
    const s = segments.find((x) => x.segment_id === id);
    return n + (s ? Math.min(estimateTrimRemovedMs(s), 800) : 0);
  }, 0);

  const runConfirm = () => {
    if (confirm === "asides") onExcludeAsides();
    else if (confirm === "tighten") onTightenAll(tightenTargets);
    else if (confirm === "offsel") onExcludeOffSelection(offSelSegs.map((s) => s.segment_id!));
    else if (confirm === "silence") {
      const ids = selectedSegmentIds.length
        ? selectedSegmentIds
        : segments.filter((s) => !s._excluded).map((s) => s.segment_id!);
      onSilenceTrim(ids.filter(Boolean));
    }
    setConfirm(null);
  };

  return (
    <div className="smart-actions-panel">
      <strong>Smart actions</strong>
      <div className="smart-actions-grid">
        {asideSegs.length ? (
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => setConfirm("asides")}
          >
            Remove tangents ({asideSegs.length}, ~{Math.round(estAsideMs / 1000)}s)
          </button>
        ) : null}
        <button
          type="button"
          className="btn sm ghost"
          onClick={() => setConfirm("tighten")}
        >
          Tighten all pauses ({tightenTargets.length}, est. ~{Math.round(estTightenMs / 1000)}s)
        </button>
        {flaggedSegs.length ? (
          <button type="button" className="btn sm ghost" onClick={() => onOpenReview("flagged")}>
            Review flagged ({flaggedSegs.length})
          </button>
        ) : null}
        {redoSegs.length ? (
          <button type="button" className="btn sm ghost" onClick={() => onOpenReview("redo")}>
            Review redo marks ({redoSegs.length})
          </button>
        ) : null}
        {lowConfSegmentIds.size ? (
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => onOpenReview("low_confidence")}
          >
            Review low-confidence ({lowConfSegmentIds.size})
          </button>
        ) : null}
        {offSelSegs.length ? (
          <button
            type="button"
            className="btn sm ghost"
            onClick={() => setConfirm("offsel")}
          >
            Exclude off-selection ({offSelSegs.length})
          </button>
        ) : null}
        <button type="button" className="btn sm ghost" onClick={() => setConfirm("silence")}>
          Trim leading/trailing silence
          {selectedSegmentIds.length ? ` (${selectedSegmentIds.length})` : ""}
        </button>
      </div>
      {confirm ? (
        <div className="smart-actions-confirm">
          <p className="muted">Apply this batch edit? You can undo from Edit history.</p>
          <div className="btn-row">
            <button type="button" className="btn sm primary" onClick={() => void runConfirm()}>
              Confirm
            </button>
            <button type="button" className="btn sm ghost" onClick={() => setConfirm(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
