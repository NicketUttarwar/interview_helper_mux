/** Shape of POST /execute and related job-start API responses. */
export interface JobStartResponse {
  ok?: boolean;
  error?: string;
  needs_operator?: boolean;
  needs_stage_reuse?: boolean;
  stage?: string;
  awaiting_write_approval?: boolean;
  pending_write_stage?: string;
  needs_handoff_review?: boolean;
}

/** True when ok:false is an operator checkpoint, not a failed start. */
export function isOperatorGateStartResponse(res: JobStartResponse): boolean {
  if (res.ok !== false) return false;
  if (res.needs_stage_reuse && res.stage) return true;
  if (res.awaiting_write_approval && res.pending_write_stage) return true;
  if (res.needs_handoff_review) return true;
  return false;
}
