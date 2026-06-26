import type { ReuseCandidate, JourneyBlocking, RunData } from "../types";

export interface StageReuseCheckContext {
  enabled: boolean;
  blocking: boolean;
  embeddedCandidates: ReuseCandidate[];
}

function blockingMeta(run: RunData | null): JourneyBlocking | undefined {
  return run?.journey?.blocking ?? run?.blocking;
}

function candidatesFromBlocking(blocking?: JourneyBlocking): ReuseCandidate[] {
  const raw = blocking?.reuse_candidates;
  return Array.isArray(raw) && raw.length ? raw : [];
}

/** Reuse UI uses run/job payload only — never a separate HTTP fetch. */
export function resolveStageReuseCheck(
  run: RunData | null,
  stageId: string,
  stageStatus: string,
  job?: {
    needs_stage_reuse?: boolean;
    stage?: string;
    reuse_candidates?: ReuseCandidate[];
  },
): StageReuseCheckContext {
  const empty: StageReuseCheckContext = {
    enabled: false,
    blocking: false,
    embeddedCandidates: [],
  };
  if (!run || stageStatus === "done") return empty;
  if (run.meta?.stage_reuse?.[stageId]?.action) return empty;

  const blocking = blockingMeta(run);
  const jobBlocking = Boolean(job?.needs_stage_reuse && job.stage === stageId);
  const journeyBlocking = Boolean(
    blocking?.blocked &&
      blocking.reason === "stage_reuse" &&
      blocking.stage_id === stageId,
  );

  const embeddedCandidates =
    (jobBlocking && job?.reuse_candidates?.length ? job.reuse_candidates : null) ??
    (journeyBlocking ? candidatesFromBlocking(blocking) : null) ??
    [];

  if (!jobBlocking && !journeyBlocking) return empty;

  return {
    enabled: true,
    blocking: true,
    embeddedCandidates,
  };
}

/** True when reuse is blocking or pending for this stage only (not other stages). */
export function isStageReusePending(
  run: RunData | null,
  stageId: string,
  stageStatus: string,
  job?: {
    needs_stage_reuse?: boolean;
    stage?: string;
    reuse_candidates?: ReuseCandidate[];
  },
): boolean {
  return resolveStageReuseCheck(run, stageId, stageStatus, job).enabled;
}

export function stageReuseOffersJobKey(
  job?: {
    needs_stage_reuse?: boolean;
    stage?: string;
    reuse_candidates?: ReuseCandidate[];
  },
  stageId?: string,
): string {
  if (!job?.needs_stage_reuse || !job.stage || job.stage !== stageId) return "";
  if (!job.reuse_candidates?.length) return "";
  return job.reuse_candidates
    .map((c) => c.run_id)
    .sort()
    .join("|");
}
