import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { StageInfo } from "../../types";
import {
  shouldAdvanceAfterGatePost,
  shouldBlockOperatorActionsForJob,
} from "../../utils/partialAcceleratedGuard";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";

interface GapDeliveryPayload {
  gap_vo_delivery?: "chatterbox" | "record" | null;
  gap_delivery_pending?: boolean;
}

export function GapDeliveryPanel({ stage }: { stage: StageInfo }) {
  const {
    runId,
    run,
    refreshRun,
    showToast,
    advanceFromCheckpoint,
    closeActionModal,
    jobRunning,
    partialAutoGPublish,
  } = useApp();
  const [payload, setPayload] = useState<GapDeliveryPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<GapDeliveryPayload>(`/api/runs/${runId}/gap-framing`);
      setPayload(res);
    } catch (e) {
      showToast(formatApiError(e, "Load gap delivery"), "error");
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load, run?.gap_vo_delivery]);

  const choose = async (delivery: "chatterbox" | "record") => {
    if (!runId || busy || jobBlocksUi) return;
    setBusy(true);
    traceAction("gui.gap_delivery.choose", `Gap delivery: ${delivery}`, { stage: stage.id });
    try {
      await api(`/api/runs/${runId}/gap-framing/delivery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delivery }),
      });
      const refreshed = await refreshRun();
      const notice = (refreshed as { synthesis_fallback_notice?: string | null })
        ?.synthesis_fallback_notice;
      if (notice) {
        showToast(notice, "info");
      } else {
        showToast(
          delivery === "chatterbox"
            ? "Chatterbox clone selected — synthesize at G1."
            : "Record path selected — use mic at G1.",
        );
      }
      closeActionModal();
      if (shouldAdvanceAfterGatePost(refreshed ?? run)) {
        await advanceFromCheckpoint();
      }
    } catch (e) {
      showToast(formatApiError(e, "Gap delivery choice"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (payload && !payload.gap_delivery_pending && payload.gap_vo_delivery) {
    return (
      <section className="gap-delivery-panel panel-inset" data-testid="gap-delivery-panel">
        <p className="hint sm">
          ✓ Gap VO delivery: <strong>{payload.gap_vo_delivery}</strong>
        </p>
      </section>
    );
  }

  return (
    <section className="gap-delivery-panel panel-inset" data-testid="gap-delivery-panel">
      <h4>How to produce gap audio?</h4>
      <p className="hint sm">
        Default: <strong>Chatterbox clone</strong> from the approved voice reference. Alternate:
        record with your computer mic at G1.
      </p>
      <div className="pickup-speaker-actions">
        <button
          type="button"
          className="btn primary sm"
          data-testid="gap-delivery-chatterbox"
          disabled={busy || jobBlocksUi}
          onClick={() => void choose("chatterbox")}
        >
          Chatterbox clone
        </button>
        <button
          type="button"
          className="btn ghost sm"
          disabled={busy || jobBlocksUi}
          onClick={() => void choose("record")}
        >
          Record with mic
        </button>
      </div>
    </section>
  );
}
