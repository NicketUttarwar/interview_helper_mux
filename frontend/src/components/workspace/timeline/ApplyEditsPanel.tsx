import { useEffect, useMemo, useState } from "react";
import { api } from "../../../api/client";
import { useApp } from "../../../context/AppContext";
import { formatMs, nleHasOperatorEdits } from "../../../utils";
import { computeNleDiff } from "../../../utils/nleDiff";
import type { NleState, TimelineSegment, VoLine } from "../../../types";
import { ArtifactAudio } from "../../shared/ArtifactAudio";

type ApplyMode = "trim_only" | "structural" | "full_refresh";

interface Props {
  nle: NleState | null;
  runId: string | null;
  segments: TimelineSegment[];
  voLines: VoLine[];
  chapterAnchorIds: string[];
  assemblyDurationBefore: number | null;
  assemblyDurationAfter: number | null;
  previewAudioPath?: string;
  priorPreviewUrl?: string | null;
  sticky?: boolean;
  onRevert?: () => void;
  onBeforeApply: (durationMs: number | null) => void;
  onApplied: () => void;
}

export function ApplyEditsPanel({
  nle,
  runId,
  segments,
  voLines,
  chapterAnchorIds,
  assemblyDurationBefore,
  assemblyDurationAfter,
  previewAudioPath,
  priorPreviewUrl,
  sticky,
  onBeforeApply,
  onApplied,
}: Props) {
  const { executeJob, run, jobRunning, refreshRun, showToast } = useApp();
  const job = run?.job;
  const [applyMode, setApplyMode] = useState<ApplyMode>("structural");
  const [applying, setApplying] = useState(false);

  const hasEdits = nleHasOperatorEdits(nle as Record<string, unknown> | null);

  const diff = useMemo(
    () => computeNleDiff(segments, nle, { voLines, chapterAnchorIds }),
    [segments, nle, voLines, chapterAnchorIds],
  );

  useEffect(() => {
    if (job?.status === "complete" && applying) {
      setApplying(false);
      void refreshRun();
      onApplied();
      showToast(
        assemblyDurationBefore != null && assemblyDurationAfter != null
          ? `Assembly updated (${formatMs(assemblyDurationBefore)} → ${formatMs(assemblyDurationAfter)})`
          : "Timeline edits applied",
      );
    }
    if (job?.status === "error" || job?.status === "needs_operator") {
      setApplying(false);
    }
  }, [
    job?.status,
    applying,
    refreshRun,
    onApplied,
    showToast,
    assemblyDurationBefore,
    assemblyDurationAfter,
  ]);

  if (!hasEdits) return null;

  const delta =
    assemblyDurationBefore != null && assemblyDurationAfter != null
      ? assemblyDurationAfter - assemblyDurationBefore
      : null;

  const fullRefresh = applyMode === "full_refresh";

  return (
    <div className={`apply-edits-panel${sticky ? " apply-edits-sticky" : ""}`}>
      <p>Timeline edits detected — apply to rebuild selection, EDL, and assembly preview.</p>
      {applying || jobRunning ? (
        <p className="hint">Applying — watch progress in the live status bar and Pipeline activity log.</p>
      ) : null}

      <div className="apply-edits-diff">
        <span>{diff.excludedCount} excluded</span>
        <span>{diff.trimmedCount} trimmed</span>
        <span>{diff.redoCount} redo</span>
        {diff.reordered ? <span>reordered</span> : null}
        {diff.msRemoved > 0 ? (
          <span>est. −{Math.round(diff.msRemoved / 1000)}s</span>
        ) : null}
        {diff.voConflictIds.length ? (
          <span className="warn">{diff.voConflictIds.length} VO conflicts</span>
        ) : null}
        {diff.chapterConflictIds.length ? (
          <span className="warn">{diff.chapterConflictIds.length} chapter conflicts</span>
        ) : null}
      </div>

      <fieldset className="apply-edits-modes">
        <legend>Apply mode</legend>
        <label>
          <input
            type="radio"
            name="nle-apply-mode"
            checked={applyMode === "trim_only"}
            onChange={() => setApplyMode("trim_only")}
          />
          Trims only (EDL + preview)
        </label>
        <label>
          <input
            type="radio"
            name="nle-apply-mode"
            checked={applyMode === "structural"}
            onChange={() => setApplyMode("structural")}
          />
          Structural (ranking + EDL when needed)
        </label>
        <label>
          <input
            type="radio"
            name="nle-apply-mode"
            checked={applyMode === "full_refresh"}
            onChange={() => setApplyMode("full_refresh")}
          />
          Full narrative refresh (+ transitions + EDL audit)
        </label>
      </fieldset>

      <div className="btn-row">
        <button
          type="button"
          className="btn sm primary"
          disabled={applying || jobRunning || job?.status === "running"}
          onClick={async () => {
            if (!runId) return;
            let before: number | null = assemblyDurationAfter;
            try {
              const asm = await api<{ timeline_duration_ms?: number }>(
                `/api/runs/${runId}/assembly-timeline`,
              );
              before = asm.timeline_duration_ms ?? before;
            } catch {
              /* ignore */
            }
            onBeforeApply(before);
            setApplying(true);
            showToast("Applying timeline edits — watch the activity log.");
            await executeJob({
              mode: "nle_apply",
              nle_full_refresh: fullRefresh,
              nle_apply_mode: applyMode,
            });
          }}
        >
          {applying || jobRunning || job?.status === "running" ? "Applying…" : "Apply timeline edits"}
        </button>
      </div>

      {delta != null ? (
        <p className="muted duration-delta">
          Assembly duration: {formatMs(assemblyDurationBefore!)} → {formatMs(assemblyDurationAfter!)}
          {delta !== 0 ? ` (${delta > 0 ? "+" : ""}${Math.round(delta / 1000)}s)` : ""}
        </p>
      ) : null}

      <div className="apply-edits-preview-row">
        {priorPreviewUrl ? (
          <div>
            <p className="muted">Before</p>
            <ArtifactAudio className="assembly-preview-player" src={priorPreviewUrl} />
          </div>
        ) : null}
        {previewAudioPath ? (
          <div>
            <p className="muted">After</p>
            <ArtifactAudio className="assembly-preview-player" src={previewAudioPath} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
