import { useMemo } from "react";
import type { RunData } from "../types";

export function usePreviewListenGate(run: RunData | null, requirePreviewListen = true) {
  return useMemo(() => {
    if (!run || !requirePreviewListen) {
      return { active: false, previewPath: null as string | null };
    }
    const milestones = run.journey?.milestones ?? run.meta?.journey_milestones ?? {};
    const previewPath = run.journey?.deliverable?.paths?.preview ?? null;
    const active = Boolean(
      milestones.preview_ready && !milestones.preview_listened && previewPath,
    );
    return { active, previewPath };
  }, [run, requirePreviewListen]);
}
