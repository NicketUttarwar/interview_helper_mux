/** Prep hooks run immediately before a step footer primary action (flush pending edits). */
const prepFns = new Map<string, () => Promise<void>>();

export function registerStepPrimaryPrep(
  key: string,
  fn: (() => Promise<void>) | null,
): void {
  if (fn) prepFns.set(key, fn);
  else prepFns.delete(key);
}

export async function runStepPrimaryPrep(key: string): Promise<void> {
  const fn = prepFns.get(key);
  if (fn) await fn();
}

export async function runStepPrimaryPreps(keys: string[]): Promise<void> {
  for (const key of keys) {
    await runStepPrimaryPrep(key);
  }
}
