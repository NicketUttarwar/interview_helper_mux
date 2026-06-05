import { useMemo } from "react";
import { nleHasOperatorEdits } from "../../../utils";
import type { NleState, RunData, TimelineSegment, VoLine } from "../../../types";

interface Props {
  run: RunData | null;
  nle: NleState | null;
  segments: TimelineSegment[];
  voLines: VoLine[];
  narrativePlan: Record<string, unknown> | null;
}

export function TimelineQcBanner({ run, nle, segments, voLines, narrativePlan }: Props) {
  const qc = run?.meta?.qc_summaries || {};

  const liveWarnings = useMemo(() => {
    const warnings: string[] = [];
    if (!nleHasOperatorEdits(nle as Record<string, unknown> | null)) return warnings;

    const overrides = nle?.segment_overrides || {};
    const excluded = new Set(
      Object.entries(overrides)
        .filter(([, ov]) => ov.excluded)
        .map(([id]) => id),
    );

    for (const line of voLines) {
      if (excluded.has(line.targets_segment_id)) {
        warnings.push(`VO line ${line.line_id} targets excluded segment ${line.targets_segment_id}.`);
      }
    }

    const chapters = (narrativePlan?.chapters as Array<Record<string, unknown>>) || [];
    for (const ch of chapters) {
      const anchor = String(ch.anchor_segment_id || ch.opens_with_segment_id || "");
      if (anchor && excluded.has(anchor)) {
        warnings.push(`Chapter "${ch.title || ch.chapter_title}" anchor ${anchor} is excluded.`);
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
      warnings.push(`Total trim removes ${Math.round(trimmedMs / 1000)}s — check episode length.`);
    }

    return warnings;
  }, [nle, segments, voLines, narrativePlan]);

  const qcBlocks = [
    { key: "narrative_qc", label: "Narrative QC" },
    { key: "edl_narrative_qc", label: "EDL narrative QC" },
    { key: "edl_qc", label: "EDL timeline QC" },
  ].filter((b) => qc[b.key as keyof typeof qc]);

  if (!qcBlocks.length && !liveWarnings.length) return null;

  return (
    <div className="timeline-qc-banner">
      {qcBlocks.map((b) => {
        const summary = qc[b.key as keyof typeof qc] as {
          status?: string;
          message?: string;
          errors?: string[];
        };
        const status = summary?.status || "unknown";
        return (
          <div key={b.key} className={`qc-inline-card status-${status}`}>
            <strong>{b.label}</strong>
            <span>{summary?.message || status}</span>
            {(summary?.errors || []).slice(0, 2).map((e, i) => (
              <p key={i} className="hint">
                {e}
              </p>
            ))}
          </div>
        );
      })}
      {liveWarnings.map((w) => (
        <p key={w} className="timeline-live-warning">
          {w}
        </p>
      ))}
    </div>
  );
}
