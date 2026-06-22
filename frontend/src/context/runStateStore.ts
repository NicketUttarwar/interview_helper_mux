import type { RunData } from "../types";

type Listener = (run: RunData | null, version: number) => void;

let currentRun: RunData | null = null;
let snapshotVersion = 0;
const listeners = new Set<Listener>();

export function getRunState(): { run: RunData | null; version: number } {
  return { run: currentRun, version: snapshotVersion };
}

export function setRunState(run: RunData | null): void {
  currentRun = run;
  snapshotVersion = run?.snapshot_version ?? snapshotVersion;
  listeners.forEach((fn) => fn(currentRun, snapshotVersion));
}

export function subscribeRunState(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function bumpLocalVersion(): void {
  snapshotVersion += 1;
  listeners.forEach((fn) => fn(currentRun, snapshotVersion));
}
