import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { getPrecleanBridge } from "../../context/AppContext";
import { precleanOfferSettled } from "../../utils/preclean";
import type { StageInfo } from "../../types";

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
  const { run, runId, refreshRun, executeJob, showToast } = useApp();
  const [submitting, setSubmitting] = useState(false);
  const settled = precleanOfferSettled(run?.meta?.audio_preclean, offer.checkpoint);

  useEffect(() => {
    if (settled) return;
    const bridge = getPrecleanBridge();
    if (!bridge.runId || bridge.shown.has(offer.checkpoint)) return;
    void api(`/api/runs/${bridge.runId}/preclean-offer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ checkpoint: offer.checkpoint, action: "offer" }),
    }).then(() => {
      const next = new Set(bridge.shown);
      next.add(offer.checkpoint);
      bridge.setShown?.(next);
    });
  }, [offer.checkpoint, settled]);

  if (settled) return null;

  const submit = async (action: "accept" | "dismiss") => {
    if (!runId || submitting) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${runId}/preclean-offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          checkpoint: offer.checkpoint,
          action,
          scope: offer.scope,
        }),
      });
      if (action === "accept") {
        showToast(
          offer.checkpoint === "g1_vo_pickup"
            ? "Running pickup cleaning…"
            : "Running audio cleaning…",
        );
        await executeJob({ mode: "stage", stage: "audio_preclean" });
      } else {
        showToast("Skipped audio cleaning — continuing with original audio.");
        await refreshRun();
        if (offer.checkpoint === "before_ingest") {
          await executeJob({ mode: "stage", stage: "ingest" });
        }
      }
      await refreshRun();
    } catch (e) {
      showToast(
        e instanceof ApiError ? e.message : "Could not save pre-clean choice — try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="quality-offer-card preclean-offer-card">
      <h4 className="quality-offer-title">Optional audio cleaning</h4>
      <p className="hint">{offer.prompt}</p>
      <p className="muted">
        Optional — never runs automatically. Skip to keep the original recording.
      </p>
      <div className="flow-choice preclean-offer-actions">
        <button
          type="button"
          className="btn ghost"
          disabled={submitting}
          data-testid={`preclean-dismiss-${offer.checkpoint}`}
          onClick={() => void submit("dismiss")}
        >
          Skip cleaning
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={submitting}
          data-testid={`preclean-accept-${offer.checkpoint}`}
          onClick={() => void submit("accept")}
        >
          Run cleaning
        </button>
      </div>
    </div>
  );
}
