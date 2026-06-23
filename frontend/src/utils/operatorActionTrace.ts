/** Client-side operator action trace ring buffer. */

export interface ClientTraceEntry {
  ts: string;
  action_id: string;
  message: string;
  stage?: string;
  level?: string;
  meta?: Record<string, unknown>;
}

const MAX_ENTRIES = 50;
const buffer: ClientTraceEntry[] = [];
const recentKeys = new Map<string, number>();
const DEDUPE_MS = 5000;

export function pushClientTrace(entry: Omit<ClientTraceEntry, "ts">): void {
  const now = Date.now();
  const key = entry.action_id;
  const skipDedupe = entry.level === "error" || entry.level === "action";
  if (!skipDedupe) {
    const last = recentKeys.get(key);
    if (last != null && now - last < DEDUPE_MS) return;
  }
  recentKeys.set(key, now);
  buffer.push({ ...entry, ts: new Date().toISOString() });
  while (buffer.length > MAX_ENTRIES) buffer.shift();
}

export function getClientTraceBuffer(): readonly ClientTraceEntry[] {
  return buffer;
}

export function formatClientTraceDump(): string {
  if (!buffer.length) return "";
  const lines = ["=== Client action trace (recent) ==="];
  for (const e of [...buffer].reverse().slice(0, 10)) {
    lines.push(`action_id: ${e.action_id}`);
    lines.push(`message:   ${e.message}`);
    if (e.stage) lines.push(`stage:     ${e.stage}`);
    lines.push(`at:        ${e.ts}`);
    lines.push("---");
  }
  return lines.join("\n");
}

export function clearClientTraceBuffer(): void {
  buffer.length = 0;
  recentKeys.clear();
}
