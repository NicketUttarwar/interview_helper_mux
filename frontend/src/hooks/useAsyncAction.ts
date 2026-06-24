import { useCallback, useState } from "react";
import type { ShowToastFn } from "../utils/guardBusy";

export interface UseAsyncActionOpts {
  showToast?: ShowToastFn;
  startMessage?: string;
  successMessage?: string;
  errorMessage?: string;
}

/** Consistent loading + toast wrapper for panel button handlers. */
export function useAsyncAction(label = "action") {
  const [busy, setBusy] = useState(false);

  const run = useCallback(
    async (
      fn: () => Promise<void>,
      opts: UseAsyncActionOpts = {},
    ): Promise<boolean> => {
      if (busy) return false;
      setBusy(true);
      try {
        if (opts.startMessage && opts.showToast) {
          opts.showToast(opts.startMessage, "info");
        }
        await fn();
        if (opts.successMessage && opts.showToast) {
          opts.showToast(opts.successMessage, "success");
        }
        return true;
      } catch (e) {
        const msg =
          e instanceof Error
            ? e.message
            : opts.errorMessage || `${label} failed`;
        opts.showToast?.(msg, "error");
        return false;
      } finally {
        setBusy(false);
      }
    },
    [busy, label],
  );

  return { busy, run, setBusy };
}
