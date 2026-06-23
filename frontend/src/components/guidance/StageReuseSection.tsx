import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { useStageReuseOffers } from "../../hooks/useStageReuseOffers";
import { resolveStageReuseCheck } from "../../utils/stageReuseOffers";
import { SourceAudioHashBadge } from "./SourceAudioHashBadge";
import { StageReuseOfferCard } from "./StageReuseOfferCard";
import { sourceHashShort } from "../../utils/sourceAudioHash";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";

export function StageReuseSection({ stage }: { stage: StageInfo }) {
  const { run, runId, refreshRun } = useApp();
  const reuseDecision = run?.meta?.stage_reuse?.[stage.id];
  const activeHash = sourceHashShort(run?.meta);
  const reuseCheck = resolveStageReuseCheck(run, stage.id, stage.status, run?.job);

  const { candidates, visible } = useStageReuseOffers(
    runId,
    stage.id,
    stage.status,
    run?.job,
    undefined,
    {
      skip: Boolean(reuseDecision?.action),
      hashShort: activeHash,
      run,
      onRefresh: () => void refreshRun(),
    },
  );

  if (reuseDecision?.action && stage.status !== "done") {
    const title =
      reuseDecision.action === "accept"
        ? "Reuse accepted — continuing with prior outputs"
        : "Running fresh — reuse declined";
    return (
      <section className="stage-reuse-section panel-inset stage-reuse-section--done" aria-label="Previous execution reuse">
        <StepDoneBanner variant="substep" title={title} />
      </section>
    );
  }

  if (stage.status === "done") return null;
  if (!visible) return null;

  return (
    <section className="stage-reuse-section panel-inset" aria-label="Previous execution reuse">
      <div className="stage-reuse-section-head">
        <div>
          <h3 className="stage-outputs-title">Previous execution reuse</h3>
          <p className="hint stage-reuse-section-lead">
            Reuse is offered only when a prior run used the same source audio hash and completed
            this step with all required outputs. Otherwise run <strong>{stage.title}</strong> fresh.
          </p>
        </div>
        {activeHash ? (
          <SourceAudioHashBadge
            hashShort={activeHash}
            hashFull={run?.meta?.source_audio_hash}
            label="This run"
          />
        ) : null}
      </div>

      {candidates.length ? (
        <StageReuseOfferCard
          stage={stage}
          candidates={candidates}
          currentHashShort={activeHash}
        />
      ) : reuseCheck.blocking ? (
        <p className="hint stage-reuse-loading">
          Reuse is pending but no prior outputs were found. Use <strong>Run fresh</strong> below or
          refresh the run.
        </p>
      ) : null}
    </section>
  );
}
