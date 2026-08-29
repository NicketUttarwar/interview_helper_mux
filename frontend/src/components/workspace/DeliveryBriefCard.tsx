import { useCallback, useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";

interface DeliveryBrief {
  target_duration_sec?: { min?: number; ideal?: number; max?: number };
  question_budget?: { min?: number; ideal?: number; max?: number };
  chapter_budget?: { min?: number; ideal?: number; max?: number };
  selection_mode?: string;
  sfx_density?: Record<string, number>;
  rationale?: string[];
}

export function DeliveryBriefCard() {
  const { runId, run, refreshRun, showToast, jobRunning, actionBusy, partialAutoGPublish } = useApp();
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);
  const [brief, setBrief] = useState<DeliveryBrief | null>(null);
  const [idealSec, setIdealSec] = useState("");
  const [qIdeal, setQIdeal] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<{ brief: DeliveryBrief | null }>(`/api/runs/${runId}/delivery-brief`);
      const b = res.brief ?? (run as { delivery_brief?: DeliveryBrief } | null)?.delivery_brief ?? null;
      setBrief(b);
      setIdealSec(String(b?.target_duration_sec?.ideal ?? ""));
      setQIdeal(String(b?.question_budget?.ideal ?? ""));
    } catch {
      setBrief((run as { delivery_brief?: DeliveryBrief } | null)?.delivery_brief ?? null);
    }
  }, [runId, run]);

  useEffect(() => {
    void load();
  }, [load, (run as { delivery_brief?: unknown } | null)?.delivery_brief]);

  if (!brief && !idealSec) return null;

  const save = async () => {
    if (!runId || busy) return;
    if (jobBlocksUi || actionBusy) {
      showToast("Busy — wait for the current job.", "warning");
      return;
    }
    setBusy(true);
    traceAction("gui.delivery_brief.save", "Saving delivery brief overrides", {
      stage: "delivery_brief_build",
    });
    try {
      const body: Record<string, unknown> = { operator_overrides: {} as Record<string, unknown> };
      const overrides = body.operator_overrides as Record<string, unknown>;
      if (idealSec.trim()) {
        overrides.target_duration_sec = { ideal: Number(idealSec) };
      }
      if (qIdeal.trim()) {
        overrides.question_budget = { ideal: Number(qIdeal) };
      }
      await api(`/api/runs/${runId}/delivery-brief`, { method: "PATCH", body: JSON.stringify(body) });
      showToast("Delivery brief saved.");
      await load();
      await refreshRun();
    } catch (e) {
      showToast(formatApiError(e, "Save delivery brief"), "error");
    } finally {
      setBusy(false);
    }
  };

  const rebuild = async () => {
    if (!runId || busy) return;
    if (jobBlocksUi || actionBusy) {
      showToast("Busy — wait for the current job.", "warning");
      return;
    }
    setBusy(true);
    traceAction("gui.delivery_brief.reset", "Rebuilding delivery brief", {
      stage: "delivery_brief_build",
    });
    try {
      await api(`/api/runs/${runId}/delivery-brief/rebuild`, { method: "POST" });
      showToast("Delivery brief rebuilt.");
      await load();
      await refreshRun();
    } catch (e) {
      showToast(formatApiError(e, "Rebuild delivery brief"), "error");
    } finally {
      setBusy(false);
    }
  };

  const dur = brief?.target_duration_sec;
  const qb = brief?.question_budget;
  const cb = brief?.chapter_budget;

  return (
    <section className="adaptation-card panel-inset">
      <h4>Delivery brief</h4>
      <p className="muted sm">
        Soft targets for this recording — duration, questions, chapters, SFX density.
      </p>
      {dur ? (
        <p className="muted sm">
          Duration band: {dur.min ?? "—"}–{dur.max ?? "—"}s (ideal {dur.ideal ?? "—"})
        </p>
      ) : null}
      {qb ? (
        <p className="muted sm">
          Question budget: ideal {qb.ideal ?? "—"} / max {qb.max ?? "—"}
        </p>
      ) : null}
      {cb ? (
        <p className="muted sm">
          Chapters: ideal {cb.ideal ?? "—"} / max {cb.max ?? "—"}
        </p>
      ) : null}
      {brief?.selection_mode ? (
        <p className="muted sm">Selection mode: {brief.selection_mode}</p>
      ) : null}
      <div className="row gap-sm" style={{ marginTop: 8 }}>
        <label className="sm">
          Ideal seconds
          <input
            type="number"
            value={idealSec}
            onChange={(e) => setIdealSec(e.target.value)}
            data-testid="delivery-brief-ideal-sec"
          />
        </label>
        <label className="sm">
          Question ideal
          <input
            type="number"
            value={qIdeal}
            onChange={(e) => setQIdeal(e.target.value)}
            data-testid="delivery-brief-q-ideal"
          />
        </label>
      </div>
      <div className="row gap-sm" style={{ marginTop: 8 }}>
        <button
          type="button"
          className="btn sm primary"
          disabled={busy}
          data-action-id="gui.delivery_brief.save"
          data-testid="delivery-brief-save"
          onClick={() => void save()}
        >
          Save overrides
        </button>
        <button
          type="button"
          className="btn sm"
          disabled={busy}
          data-action-id="gui.delivery_brief.reset"
          data-testid="delivery-brief-rebuild"
          onClick={() => void rebuild()}
        >
          Rebuild from analysis
        </button>
      </div>
    </section>
  );
}
