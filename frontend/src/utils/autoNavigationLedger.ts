/** Tracks operator auto-navigation targets for one GUI server session (run.sh lifetime). */

const STORAGE_PREFIX = "ihm_auto_nav_";

let serverSessionId: string | null = null;
let consumedKeys = new Set<string>();

function hasSessionStorage(): boolean {
  try {
    return typeof sessionStorage !== "undefined";
  } catch {
    return false;
  }
}

export interface AutoNavTarget {
  stageId: string;
  stepId?: string | null;
}

export function autoNavTargetKey(target: AutoNavTarget): string {
  return `${target.stageId}::${target.stepId ?? ""}`;
}

export function resetAutoNavLedgerIfServerChanged(
  serverStartedAt: string | null | undefined,
): void {
  if (!serverStartedAt) return;
  if (serverSessionId === serverStartedAt) return;
  serverSessionId = serverStartedAt;
  if (!hasSessionStorage()) {
    consumedKeys = new Set();
    return;
  }
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + serverStartedAt);
    consumedKeys = new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    consumedKeys = new Set();
  }
}

function persistLedger(): void {
  if (!serverSessionId || !hasSessionStorage()) return;
  try {
    sessionStorage.setItem(
      STORAGE_PREFIX + serverSessionId,
      JSON.stringify([...consumedKeys]),
    );
  } catch {
    /* quota / private mode */
  }
}

export function isAutoNavConsumed(target: AutoNavTarget): boolean {
  return consumedKeys.has(autoNavTargetKey(target));
}

export function markAutoNavConsumed(target: AutoNavTarget): void {
  const key = autoNavTargetKey(target);
  if (consumedKeys.has(key)) return;
  consumedKeys.add(key);
  persistLedger();
}

/** True when any workbench step on this stage was auto-opened this server session. */
export function stageHadAutoNavigation(stageId: string): boolean {
  const prefix = `${stageId}::`;
  for (const key of consumedKeys) {
    if (key.startsWith(prefix)) return true;
  }
  return false;
}

export function getConsumedAutoNavKeys(): ReadonlySet<string> {
  return consumedKeys;
}

/** Test helper — clear in-memory ledger without touching sessionStorage. */
export function clearAutoNavLedgerForTests(): void {
  consumedKeys = new Set();
  serverSessionId = null;
}
