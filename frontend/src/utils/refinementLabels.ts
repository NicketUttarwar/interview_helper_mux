/** Human-readable labels for Refinement Pass vocab — keep in sync with refinement_catalog.py. */

const CLASS_LABELS: Record<string, string> = {
  gap_vo: "host VO reframing",
  narrative: "narrative arc",
  ranking: "topic ranking",
  transitions: "transition bridges",
  sdp_intent: "sound design restraint",
  edl_narrative: "pre-EDL narrative sanity",
  cold_open: "cold open",
};

export function refinementClassLabel(classId: string): string {
  return CLASS_LABELS[classId] || classId.replace(/_/g, " ");
}

const REASON_CODE_LABELS: Record<string, string> = {
  disabled: "Refinement passes are disabled for this run",
  blacklist: "Blacklisted for this pass",
  not_whitelisted: "Not on the refinement whitelist",
  cap: "Second-run cap already reached (one refinement per function)",
  simple_tape: "Tape profile is simple — a single clean pass is enough",
  not_eligible: "This tape's agenda did not open this class",
  succession_locked: "Waiting on an earlier pass to unlock this one",
  mutex: "Mutually exclusive with another active refinement",
  missing_artifacts: "Required inputs are not ready yet",
  no_new_evidence: "No new evidence since the last pass — output unchanged",
  no_topic_holes: "No coverage holes found — ranking stays as-is",
  noop: "Candidate matched the draft — nothing to change",
  feasibility_orphans: "Candidate referenced dropped segments — kept the draft",
  rejected_rubric: "Candidate scored worse than the current champion — kept the champion",
};

export function refinementReasonLabel(reasonCode: string): string {
  return REASON_CODE_LABELS[reasonCode] || reasonCode.replace(/_/g, " ");
}
