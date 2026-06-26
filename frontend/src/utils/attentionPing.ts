import type { RunData } from "../types";
import { listRequiredAttentionItems } from "./attentionQueue";

/** Stable key for required operator attention — changes when a new review/action gate appears. */
export function requiredAttentionKey(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): string {
  if (!run) return "";
  return listRequiredAttentionItems(run, grants)
    .map((i) => `${i.kind}:${i.stageId}`)
    .sort()
    .join("|");
}

export function playAttentionPing(muted: boolean): void {
  if (muted) return;
  try {
    const ctx = new (window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.12;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.stop(ctx.currentTime + 0.25);
  } catch {
    /* Web Audio unavailable */
  }
}

/**
 * Play at most one attention ping when required operator attention newly appears.
 * Returns true if a ping was played.
 */
export function maybePingForRequiredAttention(
  run: RunData | null,
  muted: boolean,
  lastKeyRef: { current: string },
  grants: Record<string, boolean> = {},
): boolean {
  const key = requiredAttentionKey(run, grants);
  if (!key) {
    lastKeyRef.current = "";
    return false;
  }
  if (key === lastKeyRef.current) return false;
  lastKeyRef.current = key;
  playAttentionPing(muted);
  return true;
}
