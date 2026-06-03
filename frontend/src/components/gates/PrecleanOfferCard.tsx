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
      if (action === "accept" && offer.checkpoint === "g1_vo_pickup") {
        showToast("Running pickup pre-clean…");
        await executeJob({ mode: "stage", stage: "audio_preclean" });
      } else {
        showToast(
          action === "accept"
            ? `Saved pre-clean preference (${offer.scope}).`
            : "Pre-clean offer dismissed.",
        );
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
    <div className="quality-offer-card">
      <p className="hint">
        <strong>Quality offer:</strong> {offer.prompt}
      </p>
      <p className="muted">
        Scope: <code>{offer.scope}</code>. Optional, non-blocking, and never auto-runs.
      </p>
      <div className="flow-choice">
        <button
          type="button"
          className="btn ghost sm"
          disabled={submitting}
          data-testid={`preclean-dismiss-${offer.checkpoint}`}
          onClick={() => void submit("dismiss")}
        >
          Dismiss
        </button>
        <button
          type="button"
          className="btn primary sm"
          disabled={submitting}
          data-testid={`preclean-accept-${offer.checkpoint}`}
          onClick={() => void submit("accept")}
        >
          Accept
        </button>
      </div>
    </div>
  );
}
