import { useApp } from "../../context/AppContext";
import { useTranscriptReviewGate } from "../../hooks/useTranscriptReviewGate";
import type { ReviewGateSpec } from "../../utils/resolveReviewGate";
import type { StageInfo } from "../../types";
import { ReviewGateBannerShell } from "./ReviewGateBannerShell";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";
import { g1AutomationPending } from "../../utils/operatorGates";

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
  disabledTitle,
}: {
  busy: boolean;
  label: string;
  onClick: () => void;
  testId?: string;
  actionId?: string;
  disabled?: boolean;
  disabledTitle?: string;
}) {
  const isDisabled = busy || disabled;
  return (
    <button
      type="button"
      className="btn primary"
      data-testid={testId}
      data-action-id={actionId}
      disabled={isDisabled}
      title={isDisabled ? disabledTitle : undefined}
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
            disabled={gate.busy}
            disabledTitle={gate.busyReason ?? undefined}
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
  const synthPending = g1AutomationPending(run);

  return (
    <ReviewGateBannerShell
      title="VO pickup (G1)"
      lead={
        ready
          ? "All pickup lines are recorded — continue to delivery."
          : synthPending
            ? `Synthesizing ${missingCount} gap VO line${missingCount === 1 ? "" : "s"} (Chatterbox) — no action needed.`
            : `${missingCount} pickup line${missingCount === 1 ? "" : "s"} still need recordings before you can continue.`
      }
      ariaLabel="VO pickup"
      testId="g1-vo-gate-banner"
      actions={
        ready ? (
        <BusyButton
          busy={busy}
          label="Continue to delivery"
          testId="g1-vo-continue-banner"
          disabled={!ready}
          onClick={() => void advanceFromCheckpoint()}
        />
        ) : synthPending ? null : (
        <BusyButton
          busy={busy}
          label="Record lines below first"
          testId="g1-vo-continue-banner"
          disabled={!ready}
          onClick={() => void advanceFromCheckpoint()}
        />
        )
      }
    />
  );
}

export function StageReviewGateBanner({ spec, stage, onReviewDetail }: Props) {
  void stage;
  switch (spec.kind) {
    case "transcript_review":
      return <TranscriptReviewGateContent onReviewDetail={onReviewDetail} />;
    case "vo_contract":
      return (
        <ReviewGateBannerShell
          title="VO contract reconcile"
          lead="Artifact seating disagrees with gap_report. Automated remediation is running or retry the layup/adjudicate chain."
          ariaLabel="VO contract"
          testId="vo-contract-banner"
        />
      );
    case "vo_coverage":
      return (
        <ReviewGateBannerShell
          title="VO synthesis required"
          lead="Seated VO lines need synthesis before EDL narrative audit. Automated remediation will rewind vo_synthesize or open G1."
          ariaLabel="VO coverage"
          testId="vo-coverage-banner"
        />
      );
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
