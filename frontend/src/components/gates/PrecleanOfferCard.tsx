import { useEffect } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { getPrecleanBridge } from "../../context/AppContext";
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
  const { runId, refreshRun, executeJob, showToast } = useApp();

  useEffect(() => {
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
  }, [offer.checkpoint]);

  const submit = async (action: "accept" | "dismiss") => {
    if (!runId) return;
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
        <button type="button" className="btn ghost sm" onClick={() => void submit("dismiss")}>
          Dismiss
        </button>
        <button type="button" className="btn primary sm" onClick={() => void submit("accept")}>
          Accept
        </button>
      </div>
    </div>
  );
}
