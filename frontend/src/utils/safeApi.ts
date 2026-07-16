import { ApiError } from "../api/client";

export type PanelFetchOutcomeKind = "expected_empty" | "action_failed" | "system";

export function formatApiError(reason: unknown, label?: string): string {
  const base =
    reason instanceof ApiError
      ? reason.message
      : reason instanceof Error
        ? reason.message
        : "Request failed";
  return label ? `${label}: ${base}` : base;
}

export function isExpectedEmptyApiError(reason: unknown): boolean {
  if (!(reason instanceof ApiError)) return false;
  if (reason.status === 404) return true;
  const msg = reason.message.toLowerCase();
  return msg.includes("not found") && msg.includes("run analysis");
}

export function reportPanelFetchOutcome(opts: {
  error: unknown;
  kind: PanelFetchOutcomeKind;
  label?: string;
  appendClientLog?: (message: string, level?: string, stage?: string) => void;
  showToast?: (message: string, level?: "info" | "error" | "warning") => void;
  stage?: string;
}): string {
  const msg = formatApiError(opts.error, opts.label);
  if (opts.kind === "expected_empty") {
    return msg;
  }
  if (opts.kind === "action_failed" || opts.kind === "system") {
    opts.appendClientLog?.(msg, "error", opts.stage);
  }
  return msg;
}

export async function safeApi<T>(
  promise: Promise<T>,
  opts: {
    label?: string;
    onError?: (message: string) => void;
    fallback?: T;
  } = {},
): Promise<T | undefined> {
  try {
    return await promise;
  } catch (reason) {
    opts.onError?.(formatApiError(reason, opts.label));
    return opts.fallback;
  }
}
