import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { ALL_API_CONSENTS } from "../../utils";
import { formatTs } from "../../utils";
import { SourceAudioHashBadge } from "./SourceAudioHashBadge";
import type { ReuseCandidate, StageInfo } from "../../types";

const PREVIEW_PATHS = 4;

export function StageReuseOfferCard({
  stage,
  candidates,
  currentHashShort,
}: {
  stage: StageInfo;
  candidates: ReuseCandidate[];
  currentHashShort?: string | null;
}) {
  const { runId, refreshRun, runNextStage, showToast, beginStageExecution } = useApp();
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (!candidates.length) return null;

  const togglePaths = (runIdKey: string) => {
    setExpanded((prev) => ({ ...prev, [runIdKey]: !prev[runIdKey] }));
  };

  const submit = async (action: "accept" | "decline_and_run", sourceRunId?: string) => {
    if (!runId || submitting) return;
    setSubmitting(true);
    if (action === "accept") {
      showToast(`Reusing ${stage.title}…`);
    } else {
      showToast(`Running ${stage.title} fresh…`);
    }
    try {
      if (action === "decline_and_run") {
        const started = await beginStageExecution({
          kind: "decline_reuse_and_run",
          stageId: stage.id,
        });
        if (!started) {
          await refreshRun();
        }
        return;
      }

      await api(`/api/runs/${runId}/stages/${stage.id}/reuse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "accept",
          source_run_id: sourceRunId,
          api_consents: ALL_API_CONSENTS,
        }),
      });
      await refreshRun();
      let pending: { paths?: string[] } | null = null;
      for (let i = 0; i < 8; i++) {
        pending = await api<{ paths?: string[] }>(
          `/api/runs/${runId}/pending-writes/${stage.id}`,
        ).catch(() => null);
        if (pending?.paths?.length) break;
        await new Promise((r) => setTimeout(r, 300));
        await refreshRun();
      }
      if (pending?.paths?.length) {
        return;
      }
      await runNextStage();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Reuse action failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="stage-reuse-offer">
      <ul className="stage-reuse-candidate-list">
        {candidates.map((c) => {
          const showAll = expanded[c.run_id];
          const visiblePaths = showAll ? c.paths : c.paths.slice(0, PREVIEW_PATHS);
          const hiddenCount = Math.max(0, c.paths.length - PREVIEW_PATHS);
          const hashMatched = Boolean(
            currentHashShort &&
              c.source_audio_hash_short &&
              currentHashShort === c.source_audio_hash_short,
          );

          return (
            <li key={c.run_id} className={`stage-reuse-candidate-card${hashMatched ? " matched" : ""}`}>
              <div className="stage-reuse-candidate-head">
                <div className="stage-reuse-candidate-meta">
                  {hashMatched ? (
                    <p className="reuse-hash-match-banner">
                      <span className="reuse-match-icon" aria-hidden>
                        ✓
                      </span>
                      Same source audio hash — outputs verified complete
                    </p>
                  ) : null}
                  <div className="stage-reuse-run-title">
                    <span className="mono stage-reuse-run-id">{c.run_id}</span>
                    {c.execution_number != null ? (
                      <span className="stage-reuse-exec-badge">exec #{c.execution_number}</span>
                    ) : null}
                  </div>
                  {c.updated_at ? (
                    <p className="asset-meta muted stage-reuse-updated">
                      Last updated {formatTs(c.updated_at)}
                    </p>
                  ) : null}
                  <SourceAudioHashBadge
                    hashShort={c.source_audio_hash_short || c.hash_in_run_id}
                    hashFull={c.source_audio_hash}
                    matched={hashMatched}
                    label="Run hash"
                  />
                </div>
                <button
                  type="button"
                  className="btn primary sm stage-reuse-accept-btn"
                  data-testid="reuse-accept"
                  disabled={submitting}
                  onClick={() => void submit("accept", c.run_id)}
                >
                  Reuse outputs
                </button>
              </div>

              {c.paths.length ? (
                <div className="stage-reuse-paths">
                  <p className="stage-reuse-paths-label muted">
                    {c.paths.length} file{c.paths.length === 1 ? "" : "s"} to copy
                  </p>
                  <ul className="stage-reuse-paths-list">
                    {visiblePaths.map((p) => (
                      <li key={p}>
                        <code className="artifact-path">{p}</code>
                      </li>
                    ))}
                  </ul>
                  {hiddenCount > 0 && !showAll ? (
                    <button
                      type="button"
                      className="btn ghost sm stage-reuse-expand"
                      onClick={() => togglePaths(c.run_id)}
                    >
                      Show {hiddenCount} more
                    </button>
                  ) : null}
                  {showAll && c.paths.length > PREVIEW_PATHS ? (
                    <button
                      type="button"
                      className="btn ghost sm stage-reuse-expand"
                      onClick={() => togglePaths(c.run_id)}
                    >
                      Show fewer
                    </button>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      <div className="stage-reuse-footer">
        <p className="hint stage-reuse-footer-hint">
          No prior run with matching hash and complete outputs? Run this step fresh.
        </p>
        <button
          type="button"
          className="btn primary sm"
          data-testid="reuse-run-fresh"
          disabled={submitting}
          onClick={() => void submit("decline_and_run")}
        >
          {submitting ? (
            <>
              <span className="spinner-inline" aria-hidden /> Starting…
            </>
          ) : (
            "Run fresh"
          )}
        </button>
      </div>
    </div>
  );
}
