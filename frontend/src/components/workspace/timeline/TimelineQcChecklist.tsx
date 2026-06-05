import { useMemo } from "react";
import { nleHasOperatorEdits } from "../../../utils";
import type { NleState, RunData, TimelineSegment, VoLine } from "../../../types";
import { parseSegmentIdFromQcMessage } from "../../../utils/nleHelpers";

interface LiveWarning {
  message: string;
  segmentId?: string;
  fix?: "restore" | "review";
}

interface Props {
  run: RunData | null;
  nle: NleState | null;
  segments: TimelineSegment[];
  voLines: VoLine[];
  narrativePlan: Record<string, unknown> | null;
  onJump: (segmentId: string, startMs: number) => void;
  onRestore: (segmentId: string) => void;
  onOpenReview: () => void;
}

export function TimelineQcChecklist({
  run,
  nle,
  segments,
  voLines,
  narrativePlan,
  onJump,
  onRestore,
  onOpenReview,
}: Props) {
  const qc = run?.meta?.qc_summaries || {};

  const liveWarnings = useMemo((): LiveWarning[] => {
    const warnings: LiveWarning[] = [];
    if (!nleHasOperatorEdits(nle as Record<string, unknown> | null)) return warnings;

    const overrides = nle?.segment_overrides || {};
    const excluded = new Set(
      Object.entries(overrides)
        .filter(([, ov]) => ov.excluded)
        .map(([id]) => id),
    );

    for (const line of voLines) {
      if (excluded.has(line.targets_segment_id)) {
        warnings.push({
          message: `VO line ${line.line_id} targets excluded segment ${line.targets_segment_id}.`,
          segmentId: line.targets_segment_id,
          fix: "restore",
        });
      }
    }

    const chapters = (narrativePlan?.chapters as Array<Record<string, unknown>>) || [];
    for (const ch of chapters) {
      const anchor = String(ch.anchor_segment_id || ch.opens_with_segment_id || "");
      if (anchor && excluded.has(anchor)) {
        warnings.push({
          message: `Chapter "${ch.title || ch.chapter_title}" anchor ${anchor} is excluded.`,
          segmentId: anchor,
          fix: "restore",
        });
      }
    }

    let trimmedMs = 0;
    for (const seg of segments) {
      const sid = seg.segment_id;
      if (!sid) continue;
      const ov = overrides[sid];
      if (!ov) continue;
      const mStart = seg._manifest_start_ms ?? seg.start_ms;
      const mEnd = seg._manifest_end_ms ?? seg.end_ms;
      const curStart = ov.start_ms != null ? Number(ov.start_ms) : seg.start_ms;
      const curEnd = ov.end_ms != null ? Number(ov.end_ms) : seg.end_ms;
      trimmedMs += Math.max(0, mEnd - mStart) - (curEnd - curStart);
    }
    if (trimmedMs > 120_000) {
      warnings.push({
        message: `Total trim removes ${Math.round(trimmedMs / 1000)}s — check episode length.`,
        fix: "review",
      });
    }

    return warnings;
  }, [nle, segments, voLines, narrativePlan]);

  const qcBlocks = [
    { key: "narrative_qc", label: "Narrative QC" },
    { key: "edl_narrative_qc", label: "EDL narrative QC" },
    { key: "edl_qc", label: "EDL timeline QC" },
  ].filter((b) => qc[b.key as keyof typeof qc]);

  if (!qcBlocks.length && !liveWarnings.length) return null;

  const segById = (id: string) => segments.find((s) => s.segment_id === id);

  return (
    <div className="timeline-qc-checklist">
      {qcBlocks.map((b) => {
        const summary = qc[b.key as keyof typeof qc] as {
          status?: string;
          message?: string;
          errors?: string[];
        };
        const status = summary?.status || "unknown";
        const errors = summary?.errors || [];
        return (
          <div key={b.key} className={`qc-inline-card status-${status}`}>
            <strong>{b.label}</strong>
            <span>{summary?.message || status}</span>
            {errors.slice(0, 5).map((e, i) => {
              const sid = parseSegmentIdFromQcMessage(e);
              const seg = sid ? segById(sid) : null;
              return (
                <div key={i} className="qc-checklist-row">
                  <p className="hint">{e}</p>
                  {sid && seg ? (
                    <button
                      type="button"
                      className="btn sm ghost"
                      onClick={() => onJump(sid, seg.start_ms)}
                    >
                      Jump
                    </button>
                  ) : null}
                  <button type="button" className="btn sm ghost" onClick={onOpenReview}>
                    Review in timeline
                  </button>
                </div>
              );
            })}
          </div>
        );
      })}
      {liveWarnings.map((w) => (
        <div key={w.message} className="qc-checklist-row timeline-live-warning">
          <p>{w.message}</p>
          {w.segmentId ? (
            <>
              <button
                type="button"
                className="btn sm ghost"
                onClick={() => {
                  const seg = segById(w.segmentId!);
                  if (seg) onJump(w.segmentId!, seg.start_ms);
                }}
              >
                Jump
              </button>
              {w.fix === "restore" ? (
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={() => void onRestore(w.segmentId!)}
                >
                  Restore
                </button>
              ) : null}
            </>
          ) : w.fix === "review" ? (
            <button type="button" className="btn sm ghost" onClick={onOpenReview}>
              Open review
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}
