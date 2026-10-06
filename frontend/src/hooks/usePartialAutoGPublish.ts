import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PartialAutoGPublishState } from "../utils/partialAcceleratedGuard";
import { isPartialAcceleratedRun } from "../utils/partialAcceleratedGuard";
import type { RunData } from "../types";

/** Poll g-publish while a partially-accelerated run is active (overlay checkpoint detection). */
export function usePartialAutoGPublish(run: RunData | null): PartialAutoGPublishState | null {
  const runId = run?.run_id;
  const active = isPartialAcceleratedRun(run) && run?.meta?.partial_auto_complete !== true;
  const [payload, setPayload] = useState<PartialAutoGPublishState | null>(null);

  useEffect(() => {
    if (!runId || !active) {
      setPayload(null);
      return;
    }
    let cancelled = false;
    const load = () => {
      void api<PartialAutoGPublishState>(`/api/runs/${runId}/g-publish`)
        .then((data) => {
          if (!cancelled) setPayload(data);
        })
        .catch(() => {
          // Keep last good snapshot — a transient /g-publish failure must not
          // put the accelerated cover back over an open Ship checkpoint.
        });
    };
    load();
    const t = window.setInterval(load, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [runId, active]);

  return active ? payload : null;
}
