import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { useApp } from "../context/AppContext";
import { traceAction } from "../operator/traceAction";
import { formatApiError } from "../utils/safeApi";

export interface DecisionOption {
  label: string;
  value: unknown;
  confidence?: number | null;
}

export interface OperatorDecision {
  id: string;
  kind: "issue_choice" | "propagation" | "upstream_rerun" | "acknowledge_warning";
  headline: string;
  detail: string;
  context?: Record<string, unknown>;
  options: DecisionOption[];
  recommended?: unknown;
  status?: string;
}

export interface StageDecisionsSummary {
  stage_key: string;
  open_count: number;
  cursor: number;
  current: OperatorDecision | null;
  decisions: OperatorDecision[];
  warnings?: string[];
  ready_for_review?: boolean;
}

export function useStageDecisions(stageId: string) {
  const { runId, refreshRun, showToast, jobRunning, actionBusy } = useApp();
  const [data, setData] = useState<StageDecisionsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!runId || !stageId) return null;
    setLoading(true);
    try {
      const res = await api<StageDecisionsSummary>(
        `/api/runs/${runId}/stages/${stageId}/decisions`,
      );
      setData(res);
      return res;
    } catch (e) {
      showToast(formatApiError(e, "Could not load decisions"), "error");
      return null;
    } finally {
      setLoading(false);
    }
  }, [runId, stageId, showToast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const resolveCurrent = useCallback(
    async (choice: unknown): Promise<boolean> => {
      if (!runId || !stageId || !data?.current) return false;
      const decision = data.current;
      traceAction("gui.decision.resolve.start", `Applying decision: ${decision.headline}`, {
        stage: stageId,
        level: "action",
        meta: { decision_id: decision.id, kind: decision.kind },
      });
      setBusy(true);
      try {
        const res = await api<StageDecisionsSummary & { ok?: boolean; errors?: string[] }>(
          `/api/runs/${runId}/stages/${stageId}/decisions/${data.current.id}/resolve`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ choice }),
          },
        );
        if (res.errors?.length) {
          showToast(res.errors[0], "warning");
        }
        await refreshRun();
        const summary = await refresh();
        if (summary?.ready_for_review) {
          showToast("Decisions complete — review outputs", "success");
          traceAction("gui.decision.apply", "All decisions complete — ready for review", {
            stage: stageId,
            level: "success",
          });
        } else {
          traceAction("gui.decision.apply", "Decision applied", {
            stage: stageId,
            level: "success",
            meta: { decision_id: decision.id },
          });
        }
        return Boolean(res.ok);
      } catch (e) {
        traceAction("gui.decision.apply", formatApiError(e, "Decision apply failed"), {
          stage: stageId,
          level: "error",
        });
        showToast(formatApiError(e, "Could not apply choice"), "error");
        return false;
      } finally {
        setBusy(false);
      }
    },
    [runId, stageId, data?.current, refreshRun, refresh, showToast],
  );

  const current = data?.current ?? null;
  const openCount = data?.open_count ?? 0;
  const totalQueued = data?.decisions?.length ?? openCount;
  const cursor = data?.cursor ?? 0;
  const decisionIndex = current
    ? Math.max(1, cursor + 1)
    : openCount > 0
      ? 1
      : 0;

  return {
    loading,
    busy: busy || jobRunning || actionBusy,
    current,
    openCount,
    totalQueued,
    decisionIndex,
    readyForReview: data?.ready_for_review ?? openCount === 0,
    warnings: data?.warnings ?? [],
    refresh,
    resolveCurrent,
  };
}
