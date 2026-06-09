import type { RunData } from "../types";

export function useJourney(run: RunData | null) {
  const journey = run?.journey;
  const phase = journey?.phase ?? "prepare";
  const blocking = journey?.blocking ?? run?.blocking;
  const isBlocked = Boolean(blocking?.blocked);

  const phaseProgress = journey?.phase_progress ?? {};

  return {
    journey,
    phase,
    nextAction: journey?.next_action ?? "",
    blocking,
    isBlocked,
    phaseProgress,
    deliverable: journey?.deliverable,
    recommendedPreclean: journey?.recommended_preclean,
    openInvestigations: journey?.open_investigations ?? 0,
  };
}
