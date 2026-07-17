import type { RunMeta } from "../types";

const STORAGE_PREFIX = "mux.transcript_reuse_edit_consumed:";

export function transcriptReuseEditPending(meta?: RunMeta | null): boolean {
  return Boolean(meta?.transcript_reuse_pending_edit);
}

export function isTranscriptReuseEditConsumed(runId: string): boolean {
  try {
    return sessionStorage.getItem(`${STORAGE_PREFIX}${runId}`) === "1";
  } catch {
    return false;
  }
}

export function markTranscriptReuseEditConsumed(runId: string): void {
  try {
    sessionStorage.setItem(`${STORAGE_PREFIX}${runId}`, "1");
  } catch {
    /* private mode / quota */
  }
}

/** Transcript reuse interstitial already finished for this execution. */
export function transcriptReuseEditSettled(meta?: RunMeta | null): boolean {
  const transcribeReuse = meta?.stage_reuse?.transcribe;
  if (transcribeReuse?.action !== "accept") return false;
  return Boolean(transcribeReuse.applied_at) && !transcriptReuseEditPending(meta);
}

/**
 * Mark consumed when reuse was applied earlier and the server cleared the pending flag
 * (save, skip, or prior session) so the interstitial never reopens on this run.
 */
export function syncTranscriptReuseEditConsumed(runId: string, meta?: RunMeta | null): void {
  if (!runId) return;
  if (transcriptReuseEditSettled(meta)) {
    markTranscriptReuseEditConsumed(runId);
  }
}

/** True only when the server requests the one-time edit and this run has not consumed it. */
export function shouldOpenTranscriptReuseEdit(
  runId: string | null | undefined,
  meta?: RunMeta | null,
): boolean {
  if (!runId) return false;
  syncTranscriptReuseEditConsumed(runId, meta);
  if (!transcriptReuseEditPending(meta)) return false;
  if (isTranscriptReuseEditConsumed(runId)) return false;
  return true;
}
