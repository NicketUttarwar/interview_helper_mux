import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { formatApiError } from "../utils/safeApi";
import type {
  ArtifactIssue,
  AutoResolveResult,
  PropagationPlan,
  StageIssuesResponse,
} from "./useArtifactIssues.types";

export type {
  ArtifactIssue,
  ArtifactIssueOption,
  AutoResolveResult,
  PropagationPlan,
  RecoveryAction,
  StageIssuesResponse,
  StageIssuesSummary,
} from "./useArtifactIssues.types";

export function useArtifactIssues(stageId: string) {
  const { runId, showToast, refreshRun } = useApp();
  const [data, setData] = useState<StageIssuesResponse | null>(null);
  const [propagationPlan, setPropagationPlan] = useState<PropagationPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!runId || !stageId) return;
    setLoading(true);
    try {
      const res = await api<StageIssuesResponse>(`/api/runs/${runId}/stages/${stageId}/issues`);
      setData(res);
    } catch (e) {
      showToast(formatApiError(e, "Load artifact issues"), "error");
    } finally {
      setLoading(false);
    }
  }, [runId, stageId, showToast]);

  const loadPropagationPlan = useCallback(async () => {
    if (!runId || !stageId) return null;
    try {
      const res = await api<{ propagation_plan?: PropagationPlan }>(
        `/api/runs/${runId}/stages/${stageId}/propagation-plan`,
      );
      const plan = res.propagation_plan ?? null;
      setPropagationPlan(plan);
      return plan;
    } catch (e) {
      showToast(formatApiError(e, "Load propagation plan"), "error");
      return null;
    }
  }, [runId, stageId, showToast]);

  useEffect(() => {
    void load();
    void loadPropagationPlan();
  }, [load, loadPropagationPlan]);

  const autoResolve = useCallback(async (): Promise<AutoResolveResult | null> => {
    if (!runId || !stageId) return null;
    setBusy(true);
    try {
      const res = await api<AutoResolveResult>(
        `/api/runs/${runId}/stages/${stageId}/issues/auto-resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ autopilot: true }),
        },
      );
      if (res.propagation_plan) {
        setPropagationPlan(res.propagation_plan);
      } else {
        await loadPropagationPlan();
      }
      await load();
      await refreshRun();
      return res;
    } catch (e) {
      showToast(formatApiError(e, "Fix all"), "error");
      return null;
    } finally {
      setBusy(false);
    }
  }, [runId, stageId, load, loadPropagationPlan, refreshRun, showToast]);

  const toastForAutoResolve = useCallback(
    (res: AutoResolveResult) => {
      const outcome = res.outcome || "unknown";
      if (outcome === "success") {
        if (res.phase === "downstream_job") {
          showToast("Fixes applied — downstream re-run started", "success");
          return;
        }
        if (res.can_advance_pipeline) {
          showToast("All issues resolved — ready to save", "success");
          return;
        }
        showToast("All issues resolved", "success");
        return;
      }
      if (outcome === "manual_required") {
        showToast("Some issues need manual choices", "warning");
        return;
      }
      if (outcome === "partial") {
        showToast(res.errors?.[0] || "Partial fix — review remaining issues", "warning");
        return;
      }
      if (outcome === "cap_exhausted") {
        showToast("Auto-resolve limit reached — use manual cards", "warning");
        return;
      }
      if (outcome === "destructive_budget_exceeded") {
        showToast("Fix blocked — would delete too many segments", "error");
        return;
      }
      showToast(res.errors?.[0] || `Auto-resolve: ${outcome}`, "error");
    },
    [showToast],
  );

  const fixAllAndContinue = useCallback(async (): Promise<AutoResolveResult | null> => {
    const res = await autoResolve();
    if (res) toastForAutoResolve(res);
    return res;
  }, [autoResolve, toastForAutoResolve]);

  const autoRepair = useCallback(async () => {
    if (!runId || !stageId) return;
    setBusy(true);
    try {
      const res = await api<{ open_blocking?: number }>(
        `/api/runs/${runId}/stages/${stageId}/issues/auto-repair`,
        { method: "POST" },
      );
      await load();
      await loadPropagationPlan();
      await refreshRun();
      showToast(
        res.open_blocking
          ? `${res.open_blocking} issue(s) still need clarification`
          : "Auto-repair complete",
        res.open_blocking ? "warning" : "success",
      );
    } catch (e) {
      showToast(formatApiError(e, "Auto-repair"), "error");
    } finally {
      setBusy(false);
    }
  }, [runId, stageId, load, loadPropagationPlan, refreshRun, showToast]);

  const resolveIssue = useCallback(
    async (issueId: string, choice: unknown) => {
      if (!runId || !stageId) return;
      setBusy(true);
      try {
        await api(`/api/runs/${runId}/stages/${stageId}/issues/${issueId}/resolve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ choice }),
        });
        await load();
        await loadPropagationPlan();
        await refreshRun();
      } catch (e) {
        showToast(formatApiError(e, "Apply fix"), "error");
      } finally {
        setBusy(false);
      }
    },
    [runId, stageId, load, loadPropagationPlan, refreshRun, showToast],
  );

  const executeAction = useCallback(
    async (issueId: string, action: string, upstreamStage?: string) => {
      if (!runId || !stageId) return;
      setBusy(true);
      try {
        await api(`/api/runs/${runId}/stages/${stageId}/issues/${issueId}/execute-action`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, upstream_stage: upstreamStage }),
        });
        await load();
        await loadPropagationPlan();
        await refreshRun();
        showToast(
          action === "rerun_upstream" ? "Upstream stage re-run started" : "Action applied",
          "success",
        );
      } catch (e) {
        showToast(formatApiError(e, "Recovery action"), "error");
      } finally {
        setBusy(false);
      }
    },
    [runId, stageId, load, loadPropagationPlan, refreshRun, showToast],
  );

  const executePropagation = useCallback(async () => {
    if (!runId || !stageId || !propagationPlan?.invalidate_from) return false;
    setBusy(true);
    try {
      const rerun = propagationPlan.suggested_upstream_stage || propagationPlan.invalidate_from;
      await api(`/api/runs/${runId}/stages/${stageId}/propagation/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          invalidate_from: propagationPlan.invalidate_from,
          rerun_stages: rerun ? [rerun] : [],
        }),
      });
      await load();
      await loadPropagationPlan();
      await refreshRun();
      showToast("Downstream invalidation and re-run started", "success");
      return true;
    } catch (e) {
      showToast(formatApiError(e, "Propagation"), "error");
      return false;
    } finally {
      setBusy(false);
    }
  }, [runId, stageId, propagationPlan, load, loadPropagationPlan, refreshRun, showToast]);

  const revalidate = useCallback(async () => {
    if (!runId || !stageId) return false;
    setBusy(true);
    try {
      const res = await api<{
        ok?: boolean;
        open_blocking?: number;
        errors?: string[];
        downstream_errors?: string[];
        propagation_plan?: PropagationPlan;
      }>(`/api/runs/${runId}/stages/${stageId}/issues/revalidate`, { method: "POST" });
      if (res.propagation_plan) {
        setPropagationPlan(res.propagation_plan);
      } else {
        await loadPropagationPlan();
      }
      await load();
      await refreshRun();
      const hasDownstream = (res.downstream_errors?.length ?? 0) > 0;
      if (res.ok && !res.open_blocking && !hasDownstream) {
        showToast("Validation passed — you can save staged files", "success");
        return true;
      }
      showToast(
        res.downstream_errors?.[0] ||
          res.errors?.[0] ||
          `${res.open_blocking ?? 0} issue(s) remain`,
        "warning",
      );
      return false;
    } catch (e) {
      showToast(formatApiError(e, "Re-check"), "error");
      return false;
    } finally {
      setBusy(false);
    }
  }, [runId, stageId, load, loadPropagationPlan, refreshRun, showToast]);

  const openItems = (data?.items || []).filter(
    (it: ArtifactIssue) => it.status === "open" && it.blocking !== false,
  );
  const autoFixed = (data?.items || []).filter((it) => it.status === "auto_fixed");

  return {
    data,
    propagationPlan,
    loading,
    busy,
    openItems,
    autoFixed,
    openBlocking: data?.open_blocking ?? 0,
    canFixAll: data?.summary?.can_fix_all ?? false,
    preview: data?.summary?.preview ?? [],
    stepLabel: data?.summary?.step_label ?? data?.capabilities?.step_label ?? "Fix all & continue",
    load,
    loadPropagationPlan,
    autoRepair,
    autoResolve,
    fixAllAndContinue,
    resolveIssue,
    executeAction,
    executePropagation,
    revalidate,
  };
}
