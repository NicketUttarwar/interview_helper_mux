import { useApp } from "../../context/AppContext";
import { useTranscriptReviewGate } from "../../hooks/useTranscriptReviewGate";
import type { ReviewGateSpec } from "../../utils/resolveReviewGate";
import type { StageInfo } from "../../types";
import { ReviewGateBannerShell } from "./ReviewGateBannerShell";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";

interface Props {
  spec: ReviewGateSpec;
  stage: StageInfo;
  onReviewDetail?: () => void;
}

function BusyButton({
  busy,
  label,
  onClick,
  testId,
  actionId,
  disabled,
}: {
  busy: boolean;
  label: string;
  onClick: () => void;
  testId?: string;
  actionId?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="btn primary"
      data-testid={testId}
      data-action-id={actionId}
      disabled={busy || disabled}
      aria-busy={busy || undefined}
      onClick={onClick}
    >
      {busy ? (
        <>
          <span className="spinner-inline" aria-hidden />
          Working…
        </>
      ) : (
        label
      )}
    </button>
  );
}

function transcriptReuseAccepted(
  stageReuse: Record<string, { action?: string }> | undefined,
): boolean {
  if (!stageReuse) return false;
  return ["transcribe", "transcript_review_build", "transcript_review"].some(
    (sid) => stageReuse[sid]?.action === "accept",
  );
}

function TranscriptReviewGateContent({
  onReviewDetail,
}: {
  onReviewDetail?: () => void;
}) {
  const { run } = useApp();
  const gate = useTranscriptReviewGate(true);
  const pending = gate.pendingCount;
  const primaryLabel = "Save and complete review";
  const reused = transcriptReuseAccepted(run?.meta?.stage_reuse);

  if (gate.loading && !gate.totalCount) {
    return <ReviewGateBannerShell title="" lead="" ariaLabel="Transcript review" loading />;
  }

  if (gate.error && !gate.totalCount) {
    return (
      <ReviewGateBannerShell
        title="Finish transcript review (G0)"
        lead={gate.error}
        ariaLabel="Transcript review"
        actions={null}
      />
    );
  }

  if (!gate.ready) {
    return (
      <ReviewGateBannerShell
        title="Finish transcript review (G0)"
        lead="No review queue — run STT review prep first."
        ariaLabel="Transcript review"
        actions={null}
      />
    );
  }

  const zeroClips = gate.totalCount === 0;

  return (
    <ReviewGateBannerShell
      title="Finish transcript review (G0)"
      lead={
        zeroClips
          ? "No ranked clips flagged — save and complete to sign off G0 and continue analysis."
          : reused
          ? "Corrected transcript copied from the previous execution — edit any clips or words below, then save and complete."
          : pending > 0
            ? `${pending} of ${gate.totalCount} ranked clip${gate.totalCount === 1 ? "" : "s"} not individually reviewed. Save and complete to commit your transcript and continue the pipeline.`
            : "Review the transcript below, then save and complete to unlock analysis stages."
      }
      meta={
        zeroClips
          ? undefined
          : `${gate.reviewedCount}/${gate.totalCount} clips marked reviewed`
      }
      error={gate.error}
      testId="transcript-review-gate-banner"
      ariaLabel="Complete transcript review"
      actions={
        <>
          <BusyButton
            busy={gate.busy}
            label={primaryLabel}
            testId="accept-all-transcript-review"
            actionId="gui.transcript_review.complete"
            onClick={() =>
              void (pending > 0 ? gate.acceptAllAndProceed() : gate.completeReview())
            }
          />
          {onReviewDetail ? (
            <button
              type="button"
              className="btn ghost sm"
              disabled={gate.busy}
              onClick={onReviewDetail}
            >
              Review clips instead
            </button>
          ) : null}
        </>
      }
    />
  );
}

function SfxPromptGateContent() {
  const { approveSfxPrompts, actionBusy, jobRunning, run, partialAutoGPublish } = useApp();
  const busy = actionBusy || shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);

  return (
    <ReviewGateBannerShell
      title="Approve SFX prompts"
      lead="Edit prompts below if needed — or approve all as-is to start MMAudio generation."
      ariaLabel="SFX prompt review"
      testId="sfx-prompt-gate-banner"
      actions={
        <BusyButton
          busy={busy}
          label="Approve all prompts & proceed"
          testId="approve-all-sfx-prompts"
          onClick={() => void approveSfxPrompts()}
        />
      }
    />
  );
}

function G1VoGateContent({ missingCount }: { missingCount: number }) {
  const { advanceFromCheckpoint, actionBusy, jobRunning, run, partialAutoGPublish } = useApp();
  const busy = actionBusy || shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);
  const ready = missingCount === 0;

  return (
    <ReviewGateBannerShell
      title="VO pickup (G1)"
      lead={
        ready
          ? "All pickup lines are recorded — continue to delivery."
          : `${missingCount} pickup line${missingCount === 1 ? "" : "s"} still need recordings before you can continue.`
      }
      ariaLabel="VO pickup"
      testId="g1-vo-gate-banner"
      actions={
        <BusyButton
          busy={busy}
          label={ready ? "Continue to delivery" : "Record lines below first"}
          testId="g1-vo-continue-banner"
          disabled={!ready}
          onClick={() => void advanceFromCheckpoint()}
        />
      }
    />
  );
}

export function StageReviewGateBanner({ spec, stage, onReviewDetail }: Props) {
  void stage;
  switch (spec.kind) {
    case "transcript_review":
      return <TranscriptReviewGateContent onReviewDetail={onReviewDetail} />;
    case "llm_gate":
      return (
        <ReviewGateBannerShell
          title="LLM quality gate"
          lead="The automated quality gate rejected this stage. Re-run or discard the staged attempt."
          ariaLabel="LLM gate"
          testId="llm-gate-banner"
        />
      );
    case "sfx_prompt":
      return <SfxPromptGateContent />;
    case "g1_vo":
      return <G1VoGateContent missingCount={spec.missingCount ?? 0} />;
    default:
      return null;
  }
}
