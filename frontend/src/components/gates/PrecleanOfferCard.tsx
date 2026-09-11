import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { getPrecleanBridge } from "../../context/AppContext";
import { precleanOfferSettled } from "../../utils/preclean";
import type { StageInfo } from "../../types";

import { formatApiError } from "../../utils/safeApi";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";
interface Offer {
  checkpoint: string;
  scope: string;
  prompt: string;
}

export function PrecleanOfferCard({
  offer,
}: {
  stage: StageInfo;
  offer: Offer;
}) {
  const { run, runId, refreshRun, beginStageExecution, showToast, appendClientLog, closeActionModal, jobRunning, actionBusy, partialAutoGPublish } = useApp();
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);
  const [submitting, setSubmitting] = useState(false);
  const settled = precleanOfferSettled(run?.meta?.audio_preclean, offer.checkpoint);
  const isBeforeIngest = offer.checkpoint === "before_ingest";

  useEffect(() => {
    if (settled) return;
    const bridge = getPrecleanBridge();
    if (!bridge.runId || bridge.shown.has(offer.checkpoint)) return;
    void api(`/api/runs/${bridge.runId}/preclean-offer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ checkpoint: offer.checkpoint, action: "offer" }),
    })
      .then(() => {
        const next = new Set(bridge.shown);
        next.add(offer.checkpoint);
        bridge.setShown?.(next);
      })
      .catch((reason) => {
        const msg = formatApiError(reason, "Preclean offer");
        appendClientLog(msg, "error");
      });
  }, [offer.checkpoint, settled, appendClientLog]);

  if (settled) return null;

  const runCleaning = async () => {
    if (!runId || submitting || jobBlocksUi || actionBusy) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${runId}/preclean-offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          checkpoint: offer.checkpoint,
          action: "accept",
          scope: offer.scope,
        }),
      });
      showToast(
        offer.checkpoint === "g1_vo_pickup"
          ? "Running pickup cleaning…"
          : "Running audio cleaning…",
      );
      const started = await beginStageExecution({ kind: "execute", stageId: "audio_preclean" });
      if (started) {
        closeActionModal();
        appendClientLog(
          offer.checkpoint === "g1_vo_pickup"
            ? "Pickup cleaning started — watch the activity log for progress."
            : "Audio cleaning started — watch the activity log for progress.",
          "info",
          "audio_preclean",
        );
      } else {
        const msg =
          "Could not start audio cleaning — check Activity log or retry from the step header.";
        appendClientLog(msg, "error", "audio_preclean");
      }
      await refreshRun();
    } catch (e) {
      const msg = formatApiError(e, "Audio cleaning");
      appendClientLog(msg, "error", "audio_preclean");
    } finally {
      setSubmitting(false);
    }
  };

  const skipCleaning = async () => {
    if (!runId || submitting || jobBlocksUi || actionBusy) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${runId}/preclean-offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          checkpoint: offer.checkpoint,
          action: "dismiss",
          scope: offer.scope,
        }),
      });
      showToast("Skipped audio cleaning.");
      appendClientLog(
        isBeforeIngest
          ? "Optional pre-clean skipped — continuing without DeepFilterNet."
          : "Optional pickup cleaning skipped.",
        "info",
        "audio_preclean",
      );
      await refreshRun();
      closeActionModal();
    } catch (e) {
      const msg = formatApiError(e, "Skip audio cleaning");
      appendClientLog(msg, "error", "audio_preclean");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="quality-offer-card preclean-offer-card">
      <h4 className="quality-offer-title">
        {isBeforeIngest ? "Optional audio pre-clean" : "Optional pickup cleaning"}
      </h4>
      <p className="hint">{offer.prompt}</p>
      {run?.journey?.source_readiness?.band ? (
        <p className="muted sm">
          Source readiness: <strong>{run.journey.source_readiness.band}</strong>
          {typeof run.journey.source_readiness.score === "number"
            ? ` (${run.journey.source_readiness.score.toFixed(2)})`
            : ""}
        </p>
      ) : null}
      <p className="muted">
        {isBeforeIngest
          ? "Optional — reduces background noise on the source recording. You can Skip and ingest as-is."
          : "Optional — clean new pickup recordings before VO ingest, or Skip."}
      </p>
      <div className="flow-choice preclean-offer-actions">
        <button
          type="button"
          className="btn ghost"
          disabled={submitting || jobBlocksUi || actionBusy}
          data-testid={`preclean-skip-${offer.checkpoint}`}
          onClick={() => void skipCleaning()}
        >
          Skip
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={submitting || jobBlocksUi || actionBusy}
          data-testid={`preclean-accept-${offer.checkpoint}`}
          onClick={() => void runCleaning()}
        >
          {submitting ? (
            <>
              <span className="spinner-inline" aria-hidden /> Starting…
            </>
          ) : isBeforeIngest ? (
            "Run audio cleaning"
          ) : (
            "Run pickup cleaning"
          )}
        </button>
      </div>
    </div>
  );
}
