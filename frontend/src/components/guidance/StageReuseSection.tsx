import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { useStageReuseOffers } from "../../hooks/useStageReuseOffers";
import { SourceAudioHashBadge } from "./SourceAudioHashBadge";
import { StageReuseOfferCard } from "./StageReuseOfferCard";
import { sourceHashShort } from "../../utils/sourceAudioHash";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";

export function StageReuseSection({ stage }: { stage: StageInfo }) {
  const { run, runId } = useApp();
  const { candidates, loading, currentHashShort } = useStageReuseOffers(
    runId,
    stage.id,
    stage.status,
    run?.job,
  );

  const activeHash = sourceHashShort(run?.meta);
  const reuseDecision = run?.meta?.stage_reuse?.[stage.id];

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
  if (!loading && !candidates.length) return null;

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

      {loading ? (
        <p className="hint stage-reuse-loading">Checking for reusable prior executions…</p>
      ) : (
        <StageReuseOfferCard
          stage={stage}
          candidates={candidates}
          currentHashShort={currentHashShort || activeHash}
        />
      )}
    </section>
  );
}
