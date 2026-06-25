/** Pending checkpoint scroll — retried on pipeline overscroll refresh. */

let pendingSubstepId: string | null = null;

function resolveCheckpointSelector(substepId?: string | null): string | null {
  if (!substepId) return null;
  const raw = substepId.includes(":") ? substepId.split(":").pop() : substepId;
  return raw ? `stage-step-${raw}` : null;
}

export function tryScrollToCheckpoint(substepId?: string | null): boolean {
  if (typeof document === "undefined") return false;
  const raw = resolveCheckpointSelector(substepId);
  const target =
    (raw ? document.querySelector(`[data-testid="${raw}"]`) : null) ??
    document.querySelector(".stage-step-row--active");
  if (!target) return false;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  return true;
}

export function setPendingCheckpointScroll(substepId?: string | null): void {
  pendingSubstepId = substepId ?? null;
}

export function getPendingCheckpointScroll(): string | null {
  return pendingSubstepId;
}

export function clearPendingCheckpointScroll(): void {
  pendingSubstepId = null;
}

export function scrollToCheckpoint(substepId?: string | null): void {
  const attempt = () => {
    if (tryScrollToCheckpoint(substepId)) {
      clearPendingCheckpointScroll();
      return true;
    }
    setPendingCheckpointScroll(substepId);
    return false;
  };

  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(() => {
      if (!attempt()) requestAnimationFrame(attempt);
    });
  } else {
    attempt();
  }
}
