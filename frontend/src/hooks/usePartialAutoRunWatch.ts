import { useEffect, useRef } from "react";
import type { AppTab, RunData } from "../types";
import {
  isGPublishReviewCheckpoint,
  isPartialAcceleratedRun,
  isPartialAutoCheckpoint,
} from "../utils/partialAcceleratedGuard";
import { isJobActivelyRunning } from "../utils/jobStatus";
import type { PartialAutoGPublishState } from "../utils/partialAcceleratedGuard";

const POLL_MS = 2000;

/** Keep run snapshot fresh and auto-open operator checkpoints during partial-auto. */
export function usePartialAutoRunWatch(opts: {
  run: RunData | null;
  runId: string | null;
  gPublish: PartialAutoGPublishState | null;
  refreshRun: (opts?: { quiet?: boolean }) => Promise<RunData | null>;
  navigateToOperatorFocus: (runOverride?: RunData | null) => Promise<boolean>;
  selectStage: (stageId: string) => void | Promise<void>;
  setActiveTab: (tab: AppTab) => void;
  setJobRunning: (running: boolean) => void;
  sessionStale: boolean;
}) {
  const {
    run,
    runId,
    gPublish,
    refreshRun,
    navigateToOperatorFocus,
    selectStage,
    setActiveTab,
    setJobRunning,
    sessionStale,
  } = opts;
  const lastCheckpointKeyRef = useRef("");

  const partialActive =
    Boolean(runId) &&
    isPartialAcceleratedRun(run) &&
    run?.meta?.partial_auto_complete !== true;

  useEffect(() => {
    lastCheckpointKeyRef.current = "";
  }, [runId]);

  useEffect(() => {
    if (!partialActive || !runId || sessionStale) return;

    let cancelled = false;

    const tick = async () => {
      const refreshed = await refreshRun({ quiet: true });
      if (cancelled || !refreshed) return;

      setJobRunning(
        isPartialAutoCheckpoint(refreshed, gPublish)
          ? false
          : isJobActivelyRunning(refreshed.job),
      );

      if (!isPartialAutoCheckpoint(refreshed, gPublish)) return;

      const atGPublish = isGPublishReviewCheckpoint(gPublish, refreshed);
      const key = [
        refreshed.transcript_review_pending ? "g0" : "",
        refreshed.journey?.blocking?.reason ?? "",
        refreshed.job?.status ?? "",
        refreshed.job?.message ?? "",
        atGPublish ? "g_publish" : "",
      ].join("|");
      if (key === lastCheckpointKeyRef.current) return;
      lastCheckpointKeyRef.current = key;

      if (atGPublish) {
        setActiveTab("pipeline");
        await selectStage("podcast_publish");
        return;
      }

      await navigateToOperatorFocus(refreshed);
    };

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    partialActive,
    runId,
    sessionStale,
    refreshRun,
    navigateToOperatorFocus,
    selectStage,
    setActiveTab,
    setJobRunning,
    gPublish?.pending,
    gPublish?.package_ready,
    gPublish?.has_master,
    gPublish?.skipped,
  ]);
}
