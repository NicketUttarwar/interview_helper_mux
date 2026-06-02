import { useMemo } from "react";
import type { ExecuteBody, JourneyExecuteHint, RunData } from "../types";

export function useJourney(run: RunData | null) {
  const journey = run?.journey;
  const phase = journey?.phase ?? "prepare";
  const blocking = journey?.blocking ?? run?.blocking;
  const isBlocked = Boolean(blocking?.blocked);

  const phaseProgress = journey?.phase_progress ?? {};

  const runExecuteHint = useMemo(() => {
    const hint = journey?.execute_hint;
    if (!hint || hint.action === "checkpoint" || !hint.mode) return null;
    const body: ExecuteBody = {
      mode: hint.mode as ExecuteBody["mode"],
      from_stage: hint.from_stage,
      until_stage: hint.until_stage,
    };
    return { body, label: hint.label };
  }, [journey?.execute_hint]);

  return {
    journey,
    phase,
    nextAction: journey?.next_action ?? "",
    blocking,
    isBlocked,
    phaseProgress,
    runExecuteHint,
    deliverable: journey?.deliverable,
    recommendedPreclean: journey?.recommended_preclean,
    openInvestigations: journey?.open_investigations ?? 0,
  };
}

export function buildExecuteFromHint(hint: JourneyExecuteHint): ExecuteBody | null {
  if (hint.action === "checkpoint" || !hint.mode) return null;
  return {
    mode: hint.mode as ExecuteBody["mode"],
    from_stage: hint.from_stage,
    until_stage: hint.until_stage,
  };
}
