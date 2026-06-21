import { ApiError } from "../api/client";

export function formatApiError(reason: unknown, label?: string): string {
  const base =
    reason instanceof ApiError
      ? reason.message
      : reason instanceof Error
        ? reason.message
        : "Request failed";
  return label ? `${label}: ${base}` : base;
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
