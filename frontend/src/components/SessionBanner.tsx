import type { RunData, RunSummary } from "../types";
import { formatBrainLabel } from "../utils";

interface SessionBannerProps {
  run: RunData | null;
  previousRunSummary?: RunSummary | null;
  onReviewReuse?: () => void;
}

export function SessionBanner({
  run,
  previousRunSummary,
  onReviewReuse,
}: SessionBannerProps) {
  if (!run) return null;
  const execNum = run.execution_number ?? run.meta?.execution_number;
  const hash = run.meta?.source_audio_hash_short;
  const phase = run.journey?.phase ?? "prepare";
  const step = run.stages.find((s) => s.status !== "done" && s.status !== "locked");
  const wd = run.working_dir;
  const relWd = wd?.includes("/executions/") ? wd.split("/executions/").pop() : wd;

  return (
    <div className="session-banner" data-testid="session-banner">
      <span className="session-banner-main">
        <strong>{run.run_id}</strong>
        {execNum != null ? <span className="muted"> · #{execNum}</span> : null}
        {hash ? <span className="muted"> · {hash}</span> : null}
        {run.meta?.homunculus_version ? (
          <span className="muted" data-testid="session-brain">
            {" "}
            · {formatBrainLabel(run.meta.homunculus_version, run.meta.homunculus_kind)}
          </span>
        ) : null}
        <span className="muted"> · {phase}</span>
        {step ? (
          <span className="muted">
            {" "}
            · {step.title}
          </span>
        ) : null}
      </span>
      {relWd ? (
        <span className="session-banner-wd hint sm" title={wd}>
          {relWd ? `executions/${relWd}` : wd}
        </span>
      ) : null}
      {previousRunSummary ? (
        <button type="button" className="btn ghost sm" onClick={onReviewReuse}>
          Previous: {previousRunSummary.run_id}
          {previousRunSummary.source_audio_hash_short === hash ? " (same audio)" : ""}
        </button>
      ) : null}
    </div>
  );
}
