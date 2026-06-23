import { api } from "./client";

export interface ActionTraceEntry {
  trace_id?: string;
  ts_start?: string;
  ts_end?: string;
  action_id?: string;
  stage?: string;
  status?: string;
  summary?: string;
  command?: string[];
  http?: { method?: string; path?: string };
  detail?: Record<string, unknown>;
}

export async function fetchActionTrace(
  runId: string,
  tail = 50,
): Promise<ActionTraceEntry[]> {
  const data = await api<{ entries?: ActionTraceEntry[] }>(
    `/api/runs/${runId}/action-trace?tail=${tail}`,
  );
  return data.entries ?? [];
}

export async function dumpLastAction(runId: string): Promise<string> {
  const data = await api<{ text?: string }>(
    `/api/runs/${runId}/action-trace/dump-last`,
    { method: "POST" },
  );
  return data.text ?? "";
}
