import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { getPrecleanBridge } from "../../context/AppContext";
import { precleanOfferSettled } from "../../utils/preclean";
import type { StageInfo } from "../../types";

import { formatApiError } from "../../utils/safeApi";
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
  const { run, runId, refreshRun, beginStageExecution, showToast, appendClientLog, closeActionModal, jobRunning, actionBusy } = useApp();
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
    if (!runId || submitting || jobRunning || actionBusy) return;
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
      }
      await refreshRun();
    } catch (e) {
      const msg = formatApiError(e, "Audio cleaning");
      showToast(msg, "error");
      appendClientLog(msg, "error", "audio_preclean");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="quality-offer-card preclean-offer-card">
      <h4 className="quality-offer-title">
        {isBeforeIngest ? "Audio pre-clean" : "Optional pickup cleaning"}
      </h4>
      <p className="hint">{offer.prompt}</p>
      {isBeforeIngest ? (
        <p className="muted">Required before ingest — reduces background noise on the source recording.</p>
      ) : (
        <p className="muted">Optional — clean new pickup recordings before VO ingest.</p>
      )}
      <div className="flow-choice preclean-offer-actions">
        <button
          type="button"
          className="btn primary"
          disabled={submitting || jobRunning || actionBusy}
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
