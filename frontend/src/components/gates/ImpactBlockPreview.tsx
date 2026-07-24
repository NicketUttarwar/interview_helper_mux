import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

interface ImpactBlock {
  framing_line_ids?: string[];
  source_segment_ids?: string[];
  rationale?: string;
}

interface GapLine {
  line_id: string;
  text?: string;
  line_category?: string;
  recorded_file?: string | null;
}

interface ScriptPayload {
  lines?: GapLine[];
  plan?: {
    acts?: Array<{
      act_id?: string;
      impact_blocks?: ImpactBlock[];
    }>;
  } | null;
}

export function ImpactBlockPreview() {
  const { runId } = useApp();
  const [data, setData] = useState<ScriptPayload | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;
    const res = await api<ScriptPayload>(`/api/runs/${runId}/gap-framing/script`);
    setData(res);
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const lineById = new Map((data?.lines || []).map((l) => [l.line_id, l]));
  const blocks =
    data?.plan?.acts?.flatMap((act) => act.impact_blocks || [])?.filter(Boolean) || [];

  if (!blocks.length) {
    return null;
  }

  return (
    <section className="impact-block-preview panel-inset" data-testid="impact-block-preview">
      <h4>Impact block preview</h4>
      <p className="hint sm">Framing VO followed by the primary source clip in each impact block.</p>
      <ul className="pickup-speaker-list">
        {blocks.map((block, idx) => {
          const primary = block.source_segment_ids?.[0];
          const framingIds = block.framing_line_ids || [];
          return (
            <li key={idx} className="pickup-speaker-card vo-card">
              <strong>Block {idx + 1}</strong>
              {block.rationale ? <p className="hint sm">{block.rationale}</p> : null}
              {framingIds.map((lid) => {
                const line = lineById.get(lid);
                const voPath = line?.recorded_file;
                const audioUrl =
                  runId && voPath
                    ? `/api/runs/${runId}/audio?path=${encodeURIComponent(voPath)}`
                    : null;
                return (
                  <div key={lid} className="impact-preview-pair">
                    <p className="muted sm">
                      {lid}
                      {line?.line_category ? ` · ${line.line_category}` : ""}
                    </p>
                    <p>{line?.text || "(not synthesized yet)"}</p>
                    {audioUrl ? (
                      <audio controls preload="none" className="audio-player" src={audioUrl} />
                    ) : (
                      <p className="hint sm">VO pending at G1</p>
                    )}
                  </div>
                );
              })}
              {primary && runId ? (
                <p className="hint sm">
                  Primary clip:{" "}
                  <code>{primary}</code> — preview on timeline after EDL.
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
