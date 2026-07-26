/** Per-tab GUI session leader — prevents stale browser tabs from mutating runs. */

import type { SessionActive } from "../types";

const CLIENT_ID_KEY = "interview_mux_gui_client_id";
const CHANNEL_NAME = "interview-mux-gui-session";

export type SessionLeaderState = {
  clientInstanceId: string;
  leaderClientId: string | null;
  uiRevision: number;
  isLeader: boolean;
};

let cachedClientId: string | null = null;

export function getClientInstanceId(): string {
  if (cachedClientId) return cachedClientId;
  try {
    const existing = sessionStorage.getItem(CLIENT_ID_KEY);
    if (existing) {
      cachedClientId = existing;
      return existing;
    }
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `tab_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(CLIENT_ID_KEY, id);
    cachedClientId = id;
    return id;
  } catch {
    cachedClientId = `tab_${Date.now()}`;
    return cachedClientId;
  }
}

export function guiClientHeaders(): Record<string, string> {
  return { "X-GUI-Client-Id": getClientInstanceId() };
}

export function parseSessionLeader(
  active: Pick<SessionActive, "active_client_instance_id" | "ui_revision"> | null | undefined,
): SessionLeaderState {
  const clientInstanceId = getClientInstanceId();
  const leaderClientId = active?.active_client_instance_id ?? null;
  const uiRevision = active?.ui_revision ?? 0;
  const isLeader = !leaderClientId || leaderClientId === clientInstanceId;
  return { clientInstanceId, leaderClientId, uiRevision, isLeader };
}

export function broadcastSessionTakeover(clientInstanceId: string, uiRevision: number): void {
  try {
    const channel = new BroadcastChannel(CHANNEL_NAME);
    channel.postMessage({ type: "takeover", clientInstanceId, uiRevision });
    channel.close();
  } catch {
    /* BroadcastChannel unavailable */
  }
}

export function subscribeSessionBroadcast(
  onMessage: (msg: { type: string; clientInstanceId?: string; uiRevision?: number }) => void,
): () => void {
  try {
    const channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (ev) => {
      if (ev.data && typeof ev.data === "object") onMessage(ev.data as { type: string });
    };
    return () => channel.close();
  } catch {
    return () => {};
  }
}
