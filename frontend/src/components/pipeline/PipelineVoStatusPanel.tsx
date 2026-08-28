import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { RunData } from "../../types";

interface AdjudicateSummary {
  pipeline_mode?: RunData["pipeline_mode"];
  nugget_coverage?: number | null;
  nugget_coverage_target?: number;
  lines?: Array<{
    line_id?: string;
    status?: string;
    text_preview?: string;
  }>;
}

function formatPipelineMode(mode?: string | null): string {
  if (!mode) return "—";
  return mode.replace(/_/g, " ");
}

export function PipelineVoStatusPanel() {
  const { runId, run } = useApp();
  const [summary, setSummary] = useState<AdjudicateSummary | null>(null);

  useEffect(() => {
    if (!runId || !run) {
      setSummary(null);
      return;
    }
    const mode = run.pipeline_mode?.mode;
    if (!mode && run.meta?.homunculus_version === "0.0.0") {
      setSummary(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await api<AdjudicateSummary>(`/api/runs/${runId}/vo-pipeline-status`);
        if (!cancelled) setSummary(res);
      } catch {
        if (!cancelled) {
          setSummary({
            pipeline_mode: run.pipeline_mode ?? undefined,
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId, run?.pipeline_mode?.mode, run?.meta?.homunculus_version]);

  const pipelineMode =
    summary?.pipeline_mode?.mode || run?.pipeline_mode?.mode || null;
  const coverage = summary?.nugget_coverage;
  const target = summary?.nugget_coverage_target ?? 0.85;
  const lines = summary?.lines || [];

  if (!run || (!pipelineMode && lines.length === 0 && coverage == null)) {
    return null;
  }

  return (
    <section className="pipeline-vo-status panel-inset" data-testid="pipeline-vo-status">
      <h4>Synthetic VO path</h4>
      <div className="pipeline-vo-status-grid">
        <div>
          <span className="muted sm">Pipeline mode</span>
          <div data-testid="pipeline-mode-value">{formatPipelineMode(pipelineMode)}</div>
        </div>
        {coverage != null ? (
          <div>
            <span className="muted sm">Nugget air coverage</span>
            <div data-testid="nugget-coverage-value">
              {Math.round(coverage * 100)}%
              <span className="muted sm"> / {Math.round(target * 100)}% target</span>
            </div>
          </div>
        ) : null}
      </div>
      {lines.length > 0 ? (
        <ul className="pipeline-adjudicate-lines hint sm">
          {lines.slice(0, 6).map((row) => (
            <li key={row.line_id || row.text_preview}>
              <code>{row.line_id}</code> — {row.status || "pending"}
              {row.text_preview ? `: ${row.text_preview.slice(0, 72)}…` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
