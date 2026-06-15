import type { SfxPromptsResponse } from "../types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function api<T = unknown>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = (await res.json().catch(() => ({ detail: res.statusText }))) as {
      detail?: string | unknown;
      error?: string;
    };
    const detail =
      typeof err.detail === "string"
        ? err.detail
        : err.error || res.statusText;
    throw new ApiError(detail, res.status);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return res as unknown as T;
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
