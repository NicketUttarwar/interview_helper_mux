import { useState } from "react";
import { segmentManifestBounds, voLinesForSegment } from "../../../hooks/useTimelineEditor";
import { SEGMENT_FLAG_LABELS } from "../../../utils/nleHelpers";
import type { TimelineSegment, VoLine } from "../../../types";
import { formatMs } from "../../../utils";

interface Props {
  segment: TimelineSegment | null;
  voLines: VoLine[];
  selectionOrder: string[];
  narrativePlan: Record<string, unknown> | null;
  contentBrief: Record<string, unknown> | null;
  playheadMs: number;
  qcIssues?: string[];
  onPatch: (patch: Record<string, unknown>) => void;
  onTrim: (startMs: number, endMs: number, snap: boolean) => void;
  onSplit: () => void;
  onSnapTrim: () => void;
  onExpandSentence: () => void;
  onOpenStageTab?: () => void;
}

export function SegmentInspector({
  segment,
  voLines,
  selectionOrder,
  narrativePlan,
  contentBrief,
  playheadMs,
  qcIssues = [],
  onPatch,
  onTrim,
  onSplit,
  onSnapTrim,
  onExpandSentence,
  onOpenStageTab,
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
  const rank = selectionOrder.indexOf(segId);
  const inSelection = rank >= 0;
  const startVal = startInput || String(segment.start_ms);
  const endVal = endInput || String(segment.end_ms);

  const chapters = (narrativePlan?.chapters as Array<Record<string, unknown>>) || [];
  const anchorChapter = chapters.find(
    (ch) =>
      String(ch.anchor_segment_id || ch.opens_with_segment_id || "") === segId,
  );
  const topics = segment.topic_tags || [];
  const briefTopics = (contentBrief?.topics as Array<Record<string, unknown>>) || [];
  const briefExcerpt = briefTopics.find((t) =>
    topics.some((tag) => String(t.title || t.topic || "").toLowerCase().includes(tag.toLowerCase())),
  );

  return (
    <div className="segment-inspector">
      <div className="segment-inspector-head">
        <h4>{segId}</h4>
        {inSelection ? (
          <span className="badge in-selection">Selection #{rank + 1}</span>
        ) : (
          <span className="badge">Off selection</span>
        )}
        {segment._excluded ? <span className="badge excluded">Excluded</span> : null}
        {segment._mark_redo ? <span className="badge redo">Redo</span> : null}
      </div>
      {segment._exclude_reason ? (
        <p className="hint sm">Exclude reason: {segment._exclude_reason}</p>
      ) : null}
      {segment._omit_recovery ? (
        <p className="hint sm">Recovery path: {segment._omit_recovery}</p>
      ) : null}
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
        {segment.edge_grade || segment.boundary_confidence != null ? (
          <>
            <dt>Edge conf.</dt>
            <dd>
              {segment.edge_grade || "—"}
              {segment.boundary_confidence != null
                ? ` (${segment.boundary_confidence.toFixed(2)})`
                : ""}
            </dd>
          </>
        ) : null}
        {anchorChapter ? (
          <>
            <dt>Chapter</dt>
            <dd>{String(anchorChapter.title || anchorChapter.chapter_title || "—")}</dd>
          </>
        ) : null}
        {topics.length ? (
          <>
            <dt>Topics</dt>
            <dd>{topics.join(", ")}</dd>
          </>
        ) : null}
      </dl>

      {(segment.start_edge || segment.end_edge) && (
        <div className="segment-inspector-qc">
          <h5>Boundary edges</h5>
          <ul>
            {segment.start_edge ? (
              <li>
                Start {segment.start_edge.grade || "—"}{" "}
                {segment.start_edge.overall != null
                  ? `(${segment.start_edge.overall.toFixed(2)})`
                  : ""}
                {segment.start_edge.repaired ? " · repaired" : ""}
                {(segment.start_edge.reasons || []).length
                  ? ` — ${(segment.start_edge.reasons || []).slice(0, 4).join(", ")}`
                  : ""}
              </li>
            ) : null}
            {segment.end_edge ? (
              <li>
                End {segment.end_edge.grade || "—"}{" "}
                {segment.end_edge.overall != null
                  ? `(${segment.end_edge.overall.toFixed(2)})`
                  : ""}
                {segment.end_edge.repaired ? " · repaired" : ""}
                {(segment.end_edge.reasons || []).length
                  ? ` — ${(segment.end_edge.reasons || []).slice(0, 4).join(", ")}`
                  : ""}
              </li>
            ) : null}
          </ul>
        </div>
      )}

      {(segment.flags || []).length ? (
        <ul className="segment-inspector-flags">
          {(segment.flags || []).map((f) => (
            <li key={f} title={SEGMENT_FLAG_LABELS[f] || f}>
              {SEGMENT_FLAG_LABELS[f] || f}
            </li>
          ))}
        </ul>
      ) : null}

      {briefExcerpt ? (
        <p className="segment-inspector-brief muted">
          Brief: {String(briefExcerpt.summary || briefExcerpt.title || "").slice(0, 120)}
        </p>
      ) : null}

      {qcIssues.length ? (
        <div className="segment-inspector-qc">
          <h5>QC notes</h5>
          <ul>
            {qcIssues.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      ) : null}

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
                {!v.recorded_file && onOpenStageTab ? (
                  <button type="button" className="btn sm ghost" onClick={onOpenStageTab}>
                    Record missing
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="btn-row segment-inspector-actions">
        <button type="button" className="btn sm ghost" onClick={() => void onSnapTrim()}>
          Snap trim to words
        </button>
        <button type="button" className="btn sm ghost" onClick={() => void onExpandSentence()}>
          Expand to sentence
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
