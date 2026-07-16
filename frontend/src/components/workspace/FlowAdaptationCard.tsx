import { useCallback, useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import type { FlowAdaptation, TbiyConformanceElement } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";

interface TopologyPayload {
  topology?: { topology_class?: string; summary_plain?: string };
  adaptation?: FlowAdaptation;
}

interface SpeakersSummary {
  conversation_profile?: {
    format_class_candidate?: string;
    format_confidence?: number;
  };
  confirmed_conversation_hypothesis_id?: string | null;
  conversation_hypotheses?: { id: string }[];
  gap_sensitivity?: { notes?: string };
}

function actionLabel(action?: string): string {
  switch (action) {
    case "apply":
      return "use tape";
    case "soft":
      return "soft bias";
    case "vo_bridge":
      return "VO bridge";
    case "collapse":
      return "collapse";
    case "defer":
      return "defer";
    case "operator_only":
      return "operator";
    default:
      return action || "—";
  }
}

export function FlowAdaptationCard() {
  const { runId, run, refreshRun, showToast } = useApp();
  const [data, setData] = useState<TopologyPayload | null>(null);
  const [speakers, setSpeakers] = useState<SpeakersSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const [res, spk] = await Promise.all([
        api<TopologyPayload>(`/api/runs/${runId}/source-topology`),
        api<SpeakersSummary>(
          `/api/runs/${runId}/artifact?path=${encodeURIComponent("understanding/speakers.json")}`,
        ).catch(() => null),
      ]);
      setData(res);
      setSpeakers(spk);
    } catch {
      setData(null);
      setSpeakers(null);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load, run?.flow_adaptation]);

  const adaptation = data?.adaptation ?? run?.flow_adaptation ?? null;
  const topologyClass =
    adaptation?.topology_class ?? data?.topology?.topology_class ?? "—";
  const confirmed = Boolean(adaptation?.operator_overrides?.topology_confirmed);
  const conformance = adaptation?.tbiy_conformance;
  const scorePct =
    typeof conformance?.score?.ratio === "number"
      ? Math.round(conformance.score.ratio * 100)
      : null;
  const modes = conformance?.modes ?? {
    five_act_mode: adaptation?.five_act_mode,
    moat_mode: adaptation?.moat_mode,
    vo_bridge_priority: adaptation?.vo_bridge_priority,
  };
  const elements: TbiyConformanceElement[] = Array.isArray(conformance?.elements)
    ? conformance.elements
    : [];
  const formatCandidate = speakers?.conversation_profile?.format_class_candidate;
  const hypPending =
    (speakers?.conversation_hypotheses?.length ?? 0) > 0 &&
    !speakers?.confirmed_conversation_hypothesis_id;
  const gapNotes = speakers?.gap_sensitivity?.notes;

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
        {formatCandidate ? (
          <> · Early format: <strong>{formatCandidate}</strong></>
        ) : null}
        {hypPending ? <> · Hypothesis confirmation pending</> : null}
        {adaptation?.pickup_eligible_speaker_id ? (
          <> · Gap pickup voice: {adaptation.pickup_eligible_speaker_id}</>
        ) : null}
        {adaptation?.operator_overrides?.pickup_speaker_confirmed ? (
          <> · ✓ speaker confirmed</>
        ) : null}
        {scorePct != null ? <> · Conformance: {scorePct}%</> : null}
      </p>
      {adaptation?.summary_plain ? (
        <p className="hint sm">{adaptation.summary_plain}</p>
      ) : null}
      {gapNotes ? (
        <p className="hint sm" data-testid="gap-sensitivity-summary">
          Gap policy: {gapNotes}
        </p>
      ) : null}
      {modes?.five_act_mode || modes?.moat_mode || modes?.vo_bridge_priority ? (
        <p className="muted sm" data-testid="tbiy-conformance-modes">
          Acts: <strong>{modes.five_act_mode || "—"}</strong>
          {" · "}
          Moat: <strong>{modes.moat_mode || "—"}</strong>
          {" · "}
          VO bridges: <strong>{modes.vo_bridge_priority || "—"}</strong>
        </p>
      ) : null}
      {elements.length > 0 ? (
        <ul className="hint sm" data-testid="tbiy-conformance-elements">
          {elements.map((el) => (
            <li key={el.id || `${el.action}-${el.presence}`}>
              <strong>{(el.id || "").replace(/_/g, " ")}</strong>
              {": "}
              {actionLabel(el.action)}
              {el.presence ? ` (${el.presence})` : ""}
            </li>
          ))}
        </ul>
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
          data-action-id="gui.adaptation.confirm"
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
