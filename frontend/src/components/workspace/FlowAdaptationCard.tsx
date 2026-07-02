import { useCallback, useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import type { FlowAdaptation } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";

interface TopologyPayload {
  topology?: { topology_class?: string; summary_plain?: string };
  adaptation?: FlowAdaptation;
}

export function FlowAdaptationCard() {
  const { runId, run, refreshRun, showToast } = useApp();
  const [data, setData] = useState<TopologyPayload | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<TopologyPayload>(`/api/runs/${runId}/source-topology`);
      setData(res);
    } catch {
      setData(null);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load, run?.flow_adaptation]);

  const adaptation = data?.adaptation ?? run?.flow_adaptation ?? null;
  const topologyClass =
    adaptation?.topology_class ?? data?.topology?.topology_class ?? "—";
  const confirmed = Boolean(adaptation?.operator_overrides?.topology_confirmed);

  const confirm = async () => {
    if (!runId || busy) return;
    setBusy(true);
    traceAction("gui.adaptation.confirm", "Confirming source topology adaptation", {
      stage: "source_topology_build",
    });
    try {
      await api(`/api/runs/${runId}/flow-adaptation/confirm`, { method: "POST" });
      showToast("Topology confirmed.");
      await load();
      await refreshRun();
    } catch (e) {
      showToast(formatApiError(e, "Confirm topology"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!adaptation && !data?.topology) return null;

  return (
    <section className="adaptation-card panel-inset">
      <h4>Flow adaptation (TBIY)</h4>
      <p className="muted sm">
        Class: <strong>{topologyClass}</strong>
        {adaptation?.pickup_eligible_speaker_id ? (
          <> · Gap pickup voice: {adaptation.pickup_eligible_speaker_id}</>
        ) : null}
        {adaptation?.operator_overrides?.pickup_speaker_confirmed ? (
          <> · ✓ speaker confirmed</>
        ) : null}
      </p>
      {adaptation?.summary_plain ? (
        <p className="hint sm">{adaptation.summary_plain}</p>
      ) : null}
      {adaptation?.ranking_weights ? (
        <p className="muted sm">
          Ranking weights:{" "}
          {Object.entries(adaptation.ranking_weights)
            .map(([k, v]) => `${k}=${v}`)
            .join(", ")}
        </p>
      ) : null}
      {!confirmed ? (
        <button
          type="button"
          className="btn sm primary"
          disabled={busy}
          data-testid="confirm-topology"
          onClick={() => void confirm()}
        >
          Confirm topology
        </button>
      ) : (
        <p className="hint sm">✓ Topology confirmed</p>
      )}
    </section>
  );
}
