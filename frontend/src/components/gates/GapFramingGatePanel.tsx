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

interface HostedVoFloorSnapshot {
  status?: string;
  need?: number;
  have?: number;
  resume_producer?: string;
  prose?: string;
}

interface GapGatePayload {
  gap_framing_enabled?: boolean;
  gap_framing_decision_pending?: boolean;
  gap_fill_mode?: string;
  llm_recommended_framing?: string | null;
  llm_framing_rationale?: string | null;
  pipeline_mode?: { mode?: string; decided_by?: string } | null;
  hosted_vo_floor?: HostedVoFloorSnapshot | null;
}

function HostedVoFloorHint({ floor }: { floor: HostedVoFloorSnapshot }) {
  const status = floor.status || "unknown";
  if (status === "UNWARRANTED" || status === "WAIVED" || status === "MET") {
    return null;
  }
  const need = floor.need ?? "—";
  const have = floor.have ?? "—";
  return (
    <p className="hint sm" data-testid="hosted-vo-floor-hint">
      Hosted VO floor: {have}/{need} ({status})
      {floor.resume_producer ? ` — resume ${floor.resume_producer}` : null}
    </p>
  );
}

export function GapFramingGatePanel({ stage }: { stage: StageInfo }) {
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
  const [busy, setBusy] = useState(false);
  const [payload, setPayload] = useState<GapGatePayload | null>(null);
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<GapGatePayload>(`/api/runs/${runId}/gap-framing`);
      setPayload(res);
    } catch (e) {
      showToast(formatApiError(e, "Load gap framing gate"), "error");
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load, run?.gap_framing_enabled, run?.gap_framing_decision_pending]);

  const choose = async (enabled: boolean) => {
    if (!runId || busy || jobBlocksUi) return;
    setBusy(true);
    traceAction(
      enabled ? "gui.gap_framing.enable" : "gui.gap_framing.disable",
      enabled ? "Enabling gap framing" : "Skipping gap framing",
      { stage: stage.id },
    );
    try {
      await api(`/api/runs/${runId}/gap-framing/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      showToast(
        enabled
          ? "Gap framing enabled — confirm speaker, voice reference, and delivery next."
          : "Gap framing skipped — ranking will use source segments only.",
        enabled ? "success" : "info",
      );
      await load();
      const refreshed = await refreshRun();
      closeActionModal();
      if (shouldAdvanceAfterGatePost(refreshed ?? run)) {
        await advanceFromCheckpoint();
      }
    } catch (e) {
      showToast(formatApiError(e, "Gap framing choice"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (run?.gap_fill_mode === "skipped" && run?.gap_framing_enabled === false) {
    return (
      <section className="gap-framing-panel panel-inset" data-testid="gap-framing-panel">
        <h4>No gap framing</h4>
        <p className="hint sm">This run uses source segments and ranking only — no interviewer VO.</p>
      </section>
    );
  }

  if (payload && !payload.gap_framing_decision_pending && payload.gap_framing_enabled) {
    return (
      <section className="gap-framing-panel panel-inset" data-testid="gap-framing-panel">
        <p className="hint sm">✓ Gap framing enabled — continue with speaker and voice reference gates.</p>
        {payload.hosted_vo_floor ? <HostedVoFloorHint floor={payload.hosted_vo_floor} /> : null}
      </section>
    );
  }

  if (payload && !payload.gap_framing_decision_pending && !payload.gap_framing_enabled) {
    return null;
  }

  return (
    <section className="gap-framing-panel panel-inset" data-testid="gap-framing-panel">
      <h4>Add interviewer gap framing?</h4>
      {payload?.hosted_vo_floor ? <HostedVoFloorHint floor={payload.hosted_vo_floor} /> : null}
      {payload?.llm_recommended_framing ? (
        <p className="hint sm gap-framing-llm-hint" data-testid="gap-framing-llm-hint">
          LLM suggests:{" "}
          <strong>
            {payload.llm_recommended_framing === "yes"
              ? "Yes"
              : payload.llm_recommended_framing === "no"
                ? "No"
                : payload.llm_recommended_framing === "sparse"
                  ? "Yes (sparse)"
                  : payload.llm_recommended_framing}
          </strong>
          {payload.llm_framing_rationale
            ? ` — ${payload.llm_framing_rationale.slice(0, 160)}`
            : " — advisory only; your choice below is authoritative (2M)."}
        </p>
      ) : null}
      <p className="hint sm">
        Gap framing adds interviewer VO (questions, summaries, prefaces, bridges) — usually via a
        Chatterbox clone of the least-spoken speaker — so the episode can be clearer and shorter.
        Recommended default: <strong>Yes</strong>. You must choose before analysis continues.
      </p>
      <div className="pickup-speaker-actions">
        <button
          type="button"
          className="btn primary sm"
          data-testid="gap-framing-yes"
          disabled={busy || jobBlocksUi}
          onClick={() => void choose(true)}
        >
          Yes — add framing audio
        </button>
        <button
          type="button"
          className="btn ghost sm"
          data-testid="gap-framing-no"
          disabled={busy || jobBlocksUi}
          onClick={() => void choose(false)}
        >
          No — source only
        </button>
      </div>
    </section>
  );
}
