/** Suppress duplicate autopilot chains fired within a short window for the same stage. */
export function shouldSkipDuplicateAutoContinue(
  completedStageId: string | null | undefined,
  last: { stageId: string; at: number } | null,
  now = Date.now(),
  windowMs = 4000,
): boolean {
  if (!completedStageId || !last) return false;
  if (last.stageId !== completedStageId) return false;
  return now - last.at < windowMs;
}

export function recordAutoContinue(
  completedStageId: string | null | undefined,
  now = Date.now(),
): { stageId: string; at: number } | null {
  if (!completedStageId) return null;
  return { stageId: completedStageId, at: now };
}
