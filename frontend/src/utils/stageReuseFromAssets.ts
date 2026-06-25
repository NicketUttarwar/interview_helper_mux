import { api, ApiError } from "../api/client";
import { ALL_API_CONSENTS } from "./index";
import type { ReuseCandidate } from "../types";

export type StageReuseFromAssetsResult =
  | { status: "reused"; copied: string[]; hasStagedWrites: boolean }
  | { status: "no_candidates" }
  | { status: "failed"; message: string };

function pickBestCandidate(candidates: ReuseCandidate[]): ReuseCandidate | null {
  if (!candidates.length) return null;
  const hashMatched = candidates.find((c) => c.same_source_audio);
  return hashMatched ?? candidates[0];
}

/** Copy validated prior-run outputs from ASSETS when available for this stage. */
export async function tryAcceptStageReuseFromAssets(
  runId: string,
  stageId: string,
): Promise<StageReuseFromAssetsResult> {
  let offers: { candidates?: ReuseCandidate[]; eligible?: boolean };
  try {
    offers = await api(`/api/runs/${runId}/stages/${stageId}/reuse-offers`);
  } catch (e) {
    const message =
      e instanceof ApiError
        ? e.message
        : "Could not check prior execution outputs — please rerun.";
    return { status: "failed", message };
  }

  const candidates = offers.candidates ?? [];
  if (!offers.eligible || !candidates.length) {
    return { status: "no_candidates" };
  }

  const best = pickBestCandidate(candidates);
  if (!best) return { status: "no_candidates" };

  try {
    const res = await api<{
      ok?: boolean;
      copied?: string[];
      stage_done?: boolean;
    }>(`/api/runs/${runId}/stages/${stageId}/reuse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "accept",
        source_run_id: best.run_id,
        api_consents: ALL_API_CONSENTS,
      }),
    });

    const copied = res.copied ?? [];
    if (!copied.length && !res.stage_done) {
      return {
        status: "failed",
        message:
          "Prior outputs exist but could not be used — they may be incomplete or corrupted. Please rerun.",
      };
    }

    let hasStagedWrites = false;
    try {
      const pending = await api<{ paths?: string[] }>(
        `/api/runs/${runId}/pending-writes/${stageId}`,
      );
      hasStagedWrites = Boolean(pending?.paths?.length);
    } catch {
      hasStagedWrites = false;
    }

    return { status: "reused", copied, hasStagedWrites };
  } catch (e) {
    const message =
      e instanceof ApiError
        ? e.message
        : "Prior outputs could not be used — please rerun.";
    return { status: "failed", message };
  }
}
