import { useEffect, useState } from "react";
import { api } from "../../../api/client";
import { useApp } from "../../../context/AppContext";
import { formatMs, nleHasOperatorEdits } from "../../../utils";
import type { NleState } from "../../../types";

interface Props {
  nle: NleState | null;
  runId: string | null;
  assemblyDurationBefore: number | null;
  assemblyDurationAfter: number | null;
  previewAudioPath?: string;
  canRevert: boolean;
  onRevert: () => void;
  onBeforeApply: (durationMs: number | null) => void;
  onApplied: () => void;
}

export function ApplyEditsPanel({
  nle,
  runId,
  assemblyDurationBefore,
  assemblyDurationAfter,
  previewAudioPath,
  canRevert,
  onRevert,
  onBeforeApply,
  onApplied,
}: Props) {
  const { executeJob, run, jobRunning, refreshRun } = useApp();
  const job = run?.job;
  const [fullRefresh, setFullRefresh] = useState(false);
  const [applying, setApplying] = useState(false);

  const hasEdits = nleHasOperatorEdits(nle as Record<string, unknown> | null);

  useEffect(() => {
    if (job?.status === "complete" && applying) {
      setApplying(false);
      void refreshRun();
      onApplied();
    }
    if (job?.status === "error" || job?.status === "needs_operator") {
      setApplying(false);
    }
  }, [job?.status, applying, refreshRun, onApplied]);

  if (!hasEdits) return null;

  const delta =
    assemblyDurationBefore != null && assemblyDurationAfter != null
      ? assemblyDurationAfter - assemblyDurationBefore
      : null;

  return (
    <div className="apply-edits-panel">
      <p>Timeline edits detected — apply to rebuild selection, EDL, and assembly preview.</p>
      <label className="apply-edits-checkbox">
        <input
          type="checkbox"
          checked={fullRefresh}
          onChange={(e) => setFullRefresh(e.target.checked)}
        />
        Full narrative refresh (re-run transitions + EDL narrative audit)
      </label>
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
            await executeJob({ mode: "nle_apply", nle_full_refresh: fullRefresh });
          }}
        >
          {applying || jobRunning || job?.status === "running" ? "Applying…" : "Apply timeline edits"}
        </button>
        {canRevert ? (
          <button type="button" className="btn sm ghost" onClick={() => void onRevert()}>
            Revert last edit
          </button>
        ) : null}
      </div>
      {delta != null ? (
        <p className="muted duration-delta">
          Assembly duration: {formatMs(assemblyDurationBefore!)} → {formatMs(assemblyDurationAfter!)}
          {delta !== 0 ? ` (${delta > 0 ? "+" : ""}${Math.round(delta / 1000)}s)` : ""}
        </p>
      ) : null}
      {previewAudioPath ? (
        <audio controls className="audio-player assembly-preview-player" src={previewAudioPath} />
      ) : null}
    </div>
  );
}
