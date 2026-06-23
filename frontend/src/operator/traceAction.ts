import { pushClientTrace } from "../utils/operatorActionTrace";

export type TraceLevel = "info" | "success" | "warning" | "error" | "action";

export interface TraceActionOpts {
  level?: TraceLevel;
  stage?: string;
  meta?: Record<string, unknown>;
  /** When set, skips remote POST (local buffer only). */
  localOnly?: boolean;
}

export type TraceActionSink = (
  message: string,
  level: TraceLevel,
  actionId: string,
  stage?: string,
) => void | Promise<void>;

let sink: TraceActionSink | null = null;

export function registerTraceActionSink(fn: TraceActionSink): void {
  sink = fn;
}

/**
 * Single frontend entry for operator-visible log events.
 */
export function traceAction(
  actionId: string,
  message: string,
  opts: TraceActionOpts = {},
): void {
  const level = opts.level ?? "info";
  pushClientTrace({
    action_id: actionId,
    message,
    stage: opts.stage,
    level,
    meta: opts.meta,
  });
  if (!opts.localOnly && sink) {
    void sink(message, level, actionId, opts.stage);
  }
}

/** @deprecated Use traceAction */
export function logOperatorActionCompat(message: string, stage?: string): void {
  traceAction("gui.operator.action", message, { level: "action", stage });
}
