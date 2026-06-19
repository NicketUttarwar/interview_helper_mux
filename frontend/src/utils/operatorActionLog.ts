/** Human-readable labels for operator API actions logged to the activity stream. */
export function describeExecuteBody(body: {
  mode?: string;
  stage?: string;
  from_stage?: string;
}): string {
  const stage = body.stage || body.from_stage;
  if (stage) return `Run step: ${stage.replace(/_/g, " ")}`;
  if (body.mode) return `Run pipeline: ${body.mode.replace(/_/g, " ")}`;
  return "Run pipeline step";
}

export function describeApiPath(path: string, method = "GET"): string | null {
  const m = method.toUpperCase();
  const approve = path.match(/\/pending-writes\/([^/]+)\/approve$/);
  if (approve && m === "POST") {
    return `Save staged outputs for ${approve[1].replace(/_/g, " ")}`;
  }
  const discard = path.match(/\/pending-writes\/([^/]+)\/discard$/);
  if (discard && m === "POST") {
    return `Discard staged outputs for ${discard[1].replace(/_/g, " ")}`;
  }
  if (path.endsWith("/execute") && m === "POST") return "Start pipeline job";
  if (path.endsWith("/handoff-ack") && m === "POST") return "Acknowledge AI review";
  if (path.endsWith("/reset") && m === "POST") return "Reset pipeline from stage";
  return null;
}
