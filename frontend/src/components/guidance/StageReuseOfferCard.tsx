import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
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
  const { runId, refreshRun, executeJob, runNextStage, showToast, openActionModal } = useApp();
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (!candidates.length) return null;

  const togglePaths = (runIdKey: string) => {
    setExpanded((prev) => ({ ...prev, [runIdKey]: !prev[runIdKey] }));
  };

  const submit = async (action: "accept" | "decline", sourceRunId?: string) => {
    if (!runId || submitting) return;
    setSubmitting(true);
    if (action === "accept") {
      showToast(`Reusing ${stage.title} from ${sourceRunId}…`);
    }
    try {
      await api(`/api/runs/${runId}/stages/${stage.id}/reuse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          source_run_id: sourceRunId,
        }),
      });
      await refreshRun();
      if (action === "decline") {
        showToast(`Running ${stage.title} fresh.`);
        await executeJob({ mode: "stage", stage: stage.id });
      } else {
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
          showToast(`Reused ${stage.title} — review outputs before saving.`);
          openActionModal();
        } else {
          showToast(`Reused ${stage.title} from ${sourceRunId} — continuing.`);
          await runNextStage();
        }
      }
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : "Reuse action failed");
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
          const hashMatched =
            c.same_source_audio ||
            Boolean(
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
                      Same source audio as this run (hash verified)
                    </p>
                  ) : c.match_kind === "path" || c.match_kind === "wav" ? (
                    <p className="hint sm reuse-weak-match">
                      Matched by {c.match_kind === "path" ? "input path" : "canonical WAV"} only —
                      verify before reusing
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
          No match you trust? Run this step fresh to regenerate outputs for the current execution.
        </p>
        <button
          type="button"
          className="btn ghost sm"
          disabled={submitting}
          onClick={() => void submit("decline")}
        >
          Run fresh instead
        </button>
      </div>
    </div>
  );
}
