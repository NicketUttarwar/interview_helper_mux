import { useCallback, useEffect, useState } from "react";
import { getRefinementSummary } from "../api/client";
import type { RefinementSummary, RunData } from "../types";

const EMPTY: RefinementSummary = {};

/**
 * Fetches the read-only Refinement Pass summary (plan/champion/evidence/cascade/bible) for the
 * active run, falling back to fields already present on RunData when the backend has embedded
 * them there directly (agenda, listener outcome trajectory).
 */
export function useRefinementSummary(
  runId: string | null,
  run: RunData | null,
): RefinementSummary {
  const [summary, setSummary] = useState<RefinementSummary>(EMPTY);

  const load = useCallback(async () => {
    if (!runId) {
      setSummary(EMPTY);
      return;
    }
    try {
      const res = await getRefinementSummary(runId);
      setSummary(res || EMPTY);
    } catch {
      setSummary(EMPTY);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    ...summary,
    agenda: run?.refinement_agenda ?? summary.agenda,
    listener_outcome_trajectory:
      run?.listener_outcome_trajectory ?? summary.listener_outcome_trajectory,
    plan: run?.refinement_plan ?? summary.plan,
    champion: run?.refinement_champion ?? summary.champion,
    evidence_packets: run?.refinement_evidence_packets ?? summary.evidence_packets,
    cascade: run?.refinement_cascade ?? summary.cascade,
  };
}
