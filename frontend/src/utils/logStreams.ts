import type { JobState, LogEntry, RunData } from "../types";
import { findHandoffStage } from "./checkpoint";
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
  const focus = resolveFocusStageId(run, null);
  if (focus) return focus;
  return findLatestActiveStageId(entries);
}

/** Stage the operator should see in Activity when idle but a gate is open. */
export function resolveFocusStageId(
  run: RunData | null,
  selectedStageId: string | null | undefined,
): string | null {
  if (!run) return null;
  const job = run.job;
  if (
    job?.status === "awaiting_write_approval" ||
    job?.awaiting_write_approval
  ) {
    return job.pending_write_stage || job.stage || selectedStageId || null;
  }
  if (job?.needs_stage_reuse && job.stage) {
    return job.stage || selectedStageId || null;
  }
  const handoff = findHandoffStage(run);
  if (handoff) return handoff.id;
  if (job?.status === "gate" || job?.status === "needs_operator") {
    return job.stage || selectedStageId || null;
  }
  const actionStage = run.stages.find((s) => s.status === "action_required");
  if (actionStage) return actionStage.id;
  return selectedStageId || null;
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

/** Remove entries already shown in the pinned strip. */
export function excludePinnedEntries(
  entries: LogEntry[],
  pinned: LogEntry[],
): LogEntry[] {
  if (!pinned.length) return entries;
  const pinnedTs = new Set(pinned.map((e) => e.ts));
  return entries.filter((e) => !pinnedTs.has(e.ts));
}

/** Collapse consecutive identical message+level lines (polluted historical tail). */
export function dedupeConsecutiveLogEntries(entries: LogEntry[]): LogEntry[] {
  const out: LogEntry[] = [];
  for (const e of entries) {
    const prev = out[out.length - 1];
    if (prev && prev.message === e.message && prev.level === e.level) {
      continue;
    }
    out.push(e);
  }
  return out;
}

export function jobRunningStage(job: JobState | undefined): string | null {
  return job?.current_stage || job?.stage || null;
}

export interface PinnedAlertsOpts {
  expanded?: boolean;
  stageId?: string | null;
  maxErrors?: number;
  maxWarnings?: number;
  maxErrorsCollapsed?: number;
  maxWarningsCollapsed?: number;
}

export interface PinnedAlertsSelection {
  primaryError: LogEntry | null;
  displayedErrors: LogEntry[];
  displayedWarnings: LogEntry[];
  errorOverflow: number;
  warningOverflow: number;
  allPinned: LogEntry[];
}

/** Stable key for dismiss state in the activity alert strip. */
export function pinnedAlertKey(entry: LogEntry): string {
  return `${entry.ts}|${entry.level ?? "info"}|${entry.message}`;
}

const DEFAULT_MAX_ERRORS_EXPANDED = 2;
const DEFAULT_MAX_WARNINGS_EXPANDED = 1;

/** Select pinned errors/warnings for the activity log alert strip. */
export function selectPinnedAlerts(
  entries: LogEntry[],
  opts: PinnedAlertsOpts = {},
): PinnedAlertsSelection {
  const expanded = opts.expanded ?? false;
  const stageId = opts.stageId;
  let errors = filterErrors(entries);
  let warnings = filterWarnings(entries);
  if (stageId) {
    errors = filterByStage(errors, stageId);
    warnings = filterByStage(warnings, stageId);
  }
  errors = errors.slice(-5);
  warnings = warnings.slice(-3);
  const allPinned = [...errors, ...warnings];

  if (!expanded) {
    const primaryError = errors.length ? errors[errors.length - 1] : null;
    return {
      primaryError,
      displayedErrors: primaryError ? [primaryError] : [],
      displayedWarnings: [],
      errorOverflow: Math.max(0, errors.length - 1),
      warningOverflow: warnings.length,
      allPinned,
    };
  }

  const maxErr = opts.maxErrors ?? DEFAULT_MAX_ERRORS_EXPANDED;
  const maxWarn = opts.maxWarnings ?? DEFAULT_MAX_WARNINGS_EXPANDED;
  const displayedErrors = errors.slice(-maxErr);
  const displayedWarnings = warnings.slice(-maxWarn);
  return {
    primaryError: errors.length ? errors[errors.length - 1] : null,
    displayedErrors,
    displayedWarnings,
    errorOverflow: Math.max(0, errors.length - displayedErrors.length),
    warningOverflow: Math.max(0, warnings.length - displayedWarnings.length),
    allPinned,
  };
}

/** Legacy helper — pinned errors for Live/Step tabs (pre-selection caps). */
export function collectPinnedErrorsAndWarnings(
  entries: LogEntry[],
  activityLogTab: "live" | "step" | "all",
  opts: {
    selectedStageId?: string | null;
    run?: RunData | null;
    jobRunning?: boolean;
  },
): { errors: LogEntry[]; warnings: LogEntry[] } {
  if (activityLogTab === "all") return { errors: [], warnings: [] };
  let errors = filterErrors(entries).slice(-5);
  let warnings = filterWarnings(entries).slice(-3);
  if (activityLogTab === "step") {
    errors = filterByStage(errors, opts.selectedStageId).slice(-3);
    warnings = filterByStage(warnings, opts.selectedStageId).slice(-2);
  } else if (activityLogTab === "live") {
    const stageId = resolveLiveStageId(opts.run ?? null, Boolean(opts.jobRunning), entries);
    errors = filterByStage(errors, stageId).slice(-3);
    warnings = filterByStage(warnings, stageId).slice(-2);
  }
  return { errors, warnings };
}

