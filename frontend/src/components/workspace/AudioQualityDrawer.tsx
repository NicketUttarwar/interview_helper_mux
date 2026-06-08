import { useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import type { AudioQualityState } from "../../types";
import { useJourney } from "../../hooks/useJourney";

const CHECKPOINT_LABELS: Record<string, string> = {
  before_ingest: "Before ingest",
  g1_vo_pickup: "After VO pickup (G1)",
};

export function AudioQualityDrawer() {
  const { run, runId, config } = useApp();
  const { recommendedPreclean } = useJourney(run);
  const [open, setOpen] = useState(true);
  const [data, setData] = useState<AudioQualityState | null>(null);
  const enabled = config?.journey_ui?.enabled !== false;

  useEffect(() => {
    if (!runId || !enabled) return;
    void api<AudioQualityState>(`/api/runs/${runId}/audio-quality`).then(setData).catch(() => setData(null));
  }, [runId, enabled, run?.meta?.audio_preclean]);

  if (!run || !enabled) return null;

  return (
    <details className="audio-quality-drawer panel" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Audio quality (optional)</summary>
      {recommendedPreclean ? (
        <p className="input-label">
          Recommended now: {CHECKPOINT_LABELS[recommendedPreclean] ?? recommendedPreclean}
        </p>
      ) : null}
      <ul className="checkpoint-list">
        {(data?.checkpoints ?? []).map((cp) => (
          <li key={cp.id}>
            {CHECKPOINT_LABELS[cp.id] ?? cp.id}
            {cp.acknowledged ? " — offered" : ""}
          </li>
        ))}
      </ul>
      <p className="muted">
        Optional pre-clean offers appear in the operator checkpoint modal on the matching
        stage (Dismiss removes the card for this run).
      </p>
    </details>
  );
}
