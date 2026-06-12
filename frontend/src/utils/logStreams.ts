import type { JobState, LogEntry, RunData } from "../types";
import { isJobActivelyRunning } from "./jobStatus";
import { stageTitleById } from "./logDisplay";

const LIVE_WINDOW_MS = 60_000;

export function filterByStage(entries: LogEntry[], stageId: string | null | undefined): LogEntry[] {
  if (!stageId) return [];
  return entries.filter((e) => e.stage === stageId);
}

export function filterErrors(entries: LogEntry[]): LogEntry[] {
  return entries.filter((e) => e.level === "error");
}

export function filterWarnings(entries: LogEntry[]): LogEntry[] {
  return entries.filter((e) => e.level === "warning");
}

export function findLatestActiveStageId(
  entries: LogEntry[],
  windowMs: number = LIVE_WINDOW_MS,
): string | null {
  const cutoff = Date.now() - windowMs;
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const e = entries[i];
    if (!e.stage) continue;
    const ts = Date.parse(e.ts);
    if (!Number.isNaN(ts) && ts >= cutoff) return e.stage;
  }
  return null;
}

export function resolveLiveStageId(
  run: RunData | null,
  jobRunning: boolean,
  entries: LogEntry[],
): string | null {
  if (!run) return null;
  const job = run.job;
  if (jobRunning || isJobActivelyRunning(job)) {
    return job?.current_stage || job?.stage || null;
  }
  return findLatestActiveStageId(entries);
}

export function filterLiveStream(
  entries: LogEntry[],
  run: RunData | null,
  jobRunning: boolean,
): LogEntry[] {
  const stageId = resolveLiveStageId(run, jobRunning, entries);
  if (!stageId) return entries.slice(-20);
  return filterByStage(entries, stageId);
}

export function resolveActiveStream(
  run: RunData | null,
  jobRunning: boolean,
  entries: LogEntry[],
): { streamId: string | null; label: string; isLive: boolean } {
  const stageId = resolveLiveStageId(run, jobRunning, entries);
  const isLive = Boolean(
    run && (jobRunning || isJobActivelyRunning(run.job)) && stageId,
  );
  const label = stageId
    ? stageTitleById(run?.stages, stageId) ?? stageId
    : "Recent activity";
  return { streamId: stageId, label, isLive };
}

export function countNewSince(entries: LogEntry[], sinceTs: string | null): number {
  if (!sinceTs) return 0;
  return entries.filter((e) => e.ts > sinceTs).length;
}

export function formatStreamLabel(run: RunData | null, stageId: string | null): string {
  if (!stageId) return "All activity";
  return stageTitleById(run?.stages, stageId) ?? stageId;
}

export function latestEntry(entries: LogEntry[]): LogEntry | null {
  return entries.length ? entries[entries.length - 1] : null;
}

export function jobRunningStage(job: JobState | undefined): string | null {
  return job?.current_stage || job?.stage || null;
}
