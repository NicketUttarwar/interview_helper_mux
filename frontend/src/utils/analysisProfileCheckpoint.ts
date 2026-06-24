import { api } from "../api/client";
import type { AnalysisState } from "../types";
import type { ShowToastFn } from "./guardBusy";

export interface CompleteAnalysisProfileOpts {
  runId: string;
  /** When omitted, only verify is performed (profile already saved). */
  data?: AnalysisState;
  verify: boolean;
  refreshRun: () => Promise<unknown>;
  advanceFromCheckpoint: () => Promise<void>;
  showToast: ShowToastFn;
  appendClientLog?: (msg: string, level?: string, stage?: string) => void;
  successMessage?: string;
  setBusy?: (busy: boolean) => void;
}

/** Save profile form data, optionally verify, then advance pipeline. */
export async function completeAnalysisProfile(
  opts: CompleteAnalysisProfileOpts,
): Promise<void> {
  const {
    runId,
    data,
    verify,
    refreshRun,
    advanceFromCheckpoint,
    showToast,
    appendClientLog,
    successMessage,
  } = opts;

  opts.setBusy?.(true);
  try {
    if (data) {
      await api(`/api/runs/${runId}/analysis-profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data,
          ...(verify ? { operator_verified: true } : {}),
        }),
      });
    }
    if (verify) {
      await api(`/api/runs/${runId}/analysis-profile/verify`, { method: "POST" });
    }
    await refreshRun();
    if (verify) {
      showToast(
        successMessage ?? "Profile verified — continuing pipeline.",
        "success",
      );
      await advanceFromCheckpoint();
    } else {
      showToast("Profile saved.", "success");
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Could not update profile";
    appendClientLog?.(msg, "error", "analysis_profile");
    showToast(msg, "error");
    throw e;
  } finally {
    opts.setBusy?.(false);
  }
}
