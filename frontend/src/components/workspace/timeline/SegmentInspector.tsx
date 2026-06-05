import { useState } from "react";
import { segmentManifestBounds, voLinesForSegment } from "../../../hooks/useTimelineEditor";
import type { TimelineSegment, VoLine } from "../../../types";
import { formatMs } from "../../../utils";

interface Props {
  segment: TimelineSegment | null;
  voLines: VoLine[];
  selectionOrder: string[];
  playheadMs: number;
  onPatch: (patch: Record<string, unknown>) => void;
  onTrim: (startMs: number, endMs: number, snap: boolean) => void;
  onSplit: () => void;
  onSnapTrim: () => void;
}

export function SegmentInspector({
  segment,
  voLines,
  selectionOrder,
  playheadMs,
  onPatch,
  onTrim,
  onSplit,
  onSnapTrim,
}: Props) {
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");

  if (!segment?.segment_id) {
    return (
      <div className="segment-inspector empty">
        <p className="muted">Select a segment to inspect trim bounds, transcript, and linked VO lines.</p>
      </div>
    );
  }

  const segId = segment.segment_id;
  const bounds = segmentManifestBounds(segment);
  const linked = voLinesForSegment(voLines, segId);
  const inSelection = selectionOrder.includes(segId);
  const startVal = startInput || String(segment.start_ms);
  const endVal = endInput || String(segment.end_ms);

  return (
    <div className="segment-inspector">
      <div className="segment-inspector-head">
        <h4>{segId}</h4>
        {inSelection ? <span className="badge in-selection">In selection</span> : null}
        {segment._excluded ? <span className="badge excluded">Excluded</span> : null}
        {segment._mark_redo ? <span className="badge redo">Redo</span> : null}
      </div>
      <p className="segment-inspector-text">{segment.text || "(no transcript text)"}</p>
      <dl className="segment-inspector-meta">
        <dt>Type</dt>
        <dd>{segment.type || "—"}</dd>
        <dt>Speaker</dt>
        <dd>{segment.speaker_role || "—"}</dd>
        <dt>Duration</dt>
        <dd>{formatMs(segment.end_ms - segment.start_ms)}</dd>
        <dt>Manifest</dt>
        <dd>
          {formatMs(bounds.start)} – {formatMs(bounds.end)}
        </dd>
      </dl>

      <div className="segment-inspector-trim">
        <label>
          Start ms
          <input
            type="number"
            value={startVal}
            onChange={(e) => setStartInput(e.target.value)}
            onBlur={() => {
              const s = Number(startVal);
              const e = Number(endVal);
              if (!Number.isNaN(s) && !Number.isNaN(e)) void onTrim(s, e, false);
              setStartInput("");
              setEndInput("");
            }}
          />
        </label>
        <label>
          End ms
          <input
            type="number"
            value={endVal}
            onChange={(e) => setEndInput(e.target.value)}
            onBlur={() => {
              const s = Number(startVal);
              const e = Number(endVal);
              if (!Number.isNaN(s) && !Number.isNaN(e)) void onTrim(s, e, false);
              setStartInput("");
              setEndInput("");
            }}
          />
        </label>
      </div>

      {linked.length ? (
        <div className="segment-inspector-vo">
          <h5>Linked VO lines</h5>
          <ul>
            {linked.map((v) => (
              <li key={v.line_id} className={v.recorded_file ? "done" : "missing"}>
                {v.line_id}: {v.text?.slice(0, 60)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="btn-row segment-inspector-actions">
        <button type="button" className="btn sm ghost" onClick={() => void onSnapTrim()}>
          Snap trim to words
        </button>
        <button type="button" className="btn sm ghost" onClick={() => void onSplit()}>
          Split at {formatMs(playheadMs)}
        </button>
        <button type="button" className="btn sm ghost" onClick={() => void onPatch({ excluded: true })}>
          Exclude
        </button>
        <button
          type="button"
          className="btn sm ghost"
          onClick={() => void onPatch({ excluded: false, mark_redo: false })}
        >
          Restore
        </button>
        <button type="button" className="btn sm ghost" onClick={() => void onPatch({ mark_redo: true })}>
          Mark redo
        </button>
      </div>
    </div>
  );
}
