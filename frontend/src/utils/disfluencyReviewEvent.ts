export interface DisfluencyReviewEventLike {
  event_id: string;
  clip_path?: string;
}

export function resolveDisfluencyClipPath(event: DisfluencyReviewEventLike): string {
  if (event.clip_path) return event.clip_path;
  if (event.event_id) return `transcript/disfluency_clips/${event.event_id}.wav`;
  return "";
}

export function disfluencyClipUrl(runId: string, event: DisfluencyReviewEventLike): string {
  const path = resolveDisfluencyClipPath(event);
  if (!path) return "";
  return `/api/runs/${runId}/audio?path=${encodeURIComponent(path)}`;
}

export function firstPendingEventIndex(
  events: { review_status: string }[],
): number {
  const idx = events.findIndex((e) => e.review_status === "pending");
  return idx >= 0 ? idx : Math.max(0, events.length - 1);
}
