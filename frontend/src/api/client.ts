import type { SfxPromptsResponse } from "../types";
import { guiClientHeaders } from "../utils/sessionTabLeader";

export class ApiError extends Error {
  status: number;
  runBusy?: boolean;
  sessionSuperseded?: boolean;

  constructor(
    message: string,
    status = 0,
    opts?: { runBusy?: boolean; sessionSuperseded?: boolean },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.runBusy = opts?.runBusy;
    this.sessionSuperseded = opts?.sessionSuperseded;
  }
}

const RUN_BUSY_STATUSES = new Set([409]);
const RUN_BUSY_MAX_RETRIES = 3;
const RUN_BUSY_BACKOFF_MS = 400;

function isRunBusyError(status: number, detail: string): boolean {
  if (!RUN_BUSY_STATUSES.has(status)) return false;
  const low = detail.toLowerCase();
  return low.includes("run_busy") || low.includes("already running") || low.includes("job is already");
}

export async function api<T = unknown>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  let attempt = 0;
  while (true) {
    const headers = new Headers(opts.headers);
    for (const [key, value] of Object.entries(guiClientHeaders())) {
      if (!headers.has(key)) headers.set(key, value);
    }
    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) {
      const err = (await res.json().catch(() => ({ detail: res.statusText }))) as {
        detail?: string | unknown;
        error?: string;
      };
      const detail =
        typeof err.detail === "string"
          ? err.detail
          : typeof err.detail === "object" && err.detail && "message" in err.detail
            ? String((err.detail as { message?: string }).message || (err.detail as { error?: string }).error)
            : err.error || res.statusText;
      const detailStr = String(detail);
      if (isRunBusyError(res.status, detailStr) && attempt < RUN_BUSY_MAX_RETRIES) {
        attempt += 1;
        await new Promise((r) => setTimeout(r, RUN_BUSY_BACKOFF_MS * attempt));
        continue;
      }
      throw new ApiError(detailStr, res.status, {
        runBusy: isRunBusyError(res.status, detailStr),
        sessionSuperseded: detailStr.toLowerCase().includes("browser tab"),
      });
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json() as Promise<T>;
    return res as unknown as T;
  }
}

export function getSfxPrompts(runId: string): Promise<SfxPromptsResponse> {
  return api<SfxPromptsResponse>(`/api/runs/${runId}/sfx-prompts`);
}

export function postSfxListenResult(
  runId: string,
  body: { asset_id: string; result: "pass" | "fail"; note?: string },
): Promise<unknown> {
  return api(`/api/runs/${runId}/sfx-prompts/listen-result`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getSfxUnderSpeechUrl(runId: string, assetId: string): string {
  return `/api/runs/${runId}/audio/sfx-under-speech?asset_id=${encodeURIComponent(assetId)}`;
}
