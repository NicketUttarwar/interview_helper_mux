import { useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { useDisfluencyReviewGate } from "../../hooks/useDisfluencyReviewGate";
import { useTranscriptReviewGate } from "../../hooks/useTranscriptReviewGate";
import { completeAnalysisProfile } from "../../utils/analysisProfileCheckpoint";
import { writeApprovalPrimaryLabel } from "../../utils/writeApprovalLabels";
import { formatApiError } from "../../utils/safeApi";
import type { ReviewGateSpec } from "../../utils/resolveReviewGate";
import type { StageInfo } from "../../types";
import { ReviewGateBannerShell } from "./ReviewGateBannerShell";

const FLOW_LABELS: Record<string, string> = {
  flow1: "Flow 1 — Full podcast",
  flow2: "Flow 2 — Highlight reel",
  flow3: "Flow 3 — Show description",
};

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

function TranscriptReviewGateContent({
  onReviewDetail,
}: {
  onReviewDetail?: () => void;
}) {
  const gate = useTranscriptReviewGate(true);
  const pending = gate.pendingCount;
  const primaryLabel =
    pending > 0 ? "Accept all & proceed" : "Complete transcript review";

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
        lead="No review clips — run STT review prep first."
        ariaLabel="Transcript review"
        actions={null}
      />
    );
  }

  return (
    <ReviewGateBannerShell
      title="Finish transcript review (G0)"
      lead={
        pending > 0
          ? `${pending} of ${gate.totalCount} ranked clip${gate.totalCount === 1 ? "" : "s"} not individually reviewed. Accept the current transcript as-is to continue the pipeline.`
          : `All ${gate.totalCount} clip${gate.totalCount === 1 ? "" : "s"} reviewed — complete to unlock analysis stages.`
      }
      meta={`${gate.reviewedCount}/${gate.totalCount} clips marked reviewed`}
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

function DisfluencyReviewGateContent({ onReviewDetail }: { onReviewDetail?: () => void }) {
  const gate = useDisfluencyReviewGate(true);
  const pending = gate.pendingCount;
  const primaryLabel =
    pending > 0 ? "Accept all & proceed" : "Complete disfluency review";

  if (gate.loading && !gate.totalCount && gate.ready) {
    return <ReviewGateBannerShell title="" lead="" ariaLabel="Disfluency review" loading />;
  }

  const noEvents = gate.ready && gate.totalCount === 0;

  return (
    <ReviewGateBannerShell
      title="Finish disfluency review (G0.5)"
      lead={
        noEvents
          ? "No filler clips were extracted — complete review to continue the pipeline."
          : pending > 0
            ? `${pending} of ${gate.totalCount} filler clip${gate.totalCount === 1 ? "" : "s"} not individually reviewed. Accept all as confirmed to continue.`
            : `All ${gate.totalCount} clip${gate.totalCount === 1 ? "" : "s"} reviewed — complete to unlock later stages.`
      }
      meta={
        gate.totalCount > 0
          ? `${gate.reviewedCount}/${gate.totalCount} clips reviewed`
          : undefined
      }
      error={gate.error}
      testId="disfluency-review-gate-banner"
      ariaLabel="Complete disfluency review"
      actions={
        <>
          <BusyButton
            busy={gate.busy}
            label={primaryLabel}
            testId="accept-all-disfluency-review"
            actionId="gui.disfluency_review.complete"
            onClick={() =>
              void (pending > 0 ? gate.acceptAllAndProceed() : gate.completeReview())
            }
          />
          {onReviewDetail && gate.totalCount > 0 ? (
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

function AnalysisProfileGateContent() {
  const {
    run,
    runId,
    refreshRun,
    advanceFromCheckpoint,
    showToast,
    setCheckpointBusy,
    actionBusy,
    jobRunning,
  } = useApp();
  const [verifying, setVerifying] = useState(false);
  const verified = Boolean(run?.profile_verified);
  const ready = Boolean(run?.profile_ready_for_review);
  const busy = verifying || actionBusy || jobRunning;

  const verify = async () => {
    if (!runId || busy || verified) return;
    setVerifying(true);
    try {
      await completeAnalysisProfile({
        runId,
        verify: true,
        refreshRun,
        advanceFromCheckpoint,
        showToast,
        setBusy: setCheckpointBusy,
        successMessage: "Profile verified — continuing pipeline.",
      });
    } finally {
      setVerifying(false);
    }
  };

  if (!ready && !verified) {
    return (
      <ReviewGateBannerShell
        title="Verify analysis profile"
        lead="Understanding analysis has not finished yet — run the analysis pipeline first."
        ariaLabel="Analysis profile"
        actions={null}
      />
    );
  }

  if (verified) return null;

  return (
    <ReviewGateBannerShell
      title="Verify analysis profile"
      lead="Review themes and story fields on the Story Board if you want — or approve the profile as-is to continue."
      ariaLabel="Analysis profile"
      testId="analysis-profile-gate-banner"
      actions={
        <BusyButton
          busy={busy}
          label="Approve profile & proceed"
          testId="approve-analysis-profile"
          onClick={() => void verify()}
        />
      }
    />
  );
}

function WriteApprovalGateContent({ stage, pathCount }: { stage: StageInfo; pathCount: number }) {
  const { approveWriteAndContinue, actionBusy, jobRunning } = useApp();
  const busy = actionBusy || jobRunning;

  return (
    <ReviewGateBannerShell
      title="Review staged outputs"
      lead={
        pathCount
          ? `${pathCount} staged file${pathCount === 1 ? "" : "s"} ready to save. Skim below if you want — or save all and continue without opening each file.`
          : "Staged outputs are ready. Save all files to write them to disk and continue."
      }
      meta={pathCount ? `${pathCount} file${pathCount === 1 ? "" : "s"} pending save` : undefined}
      ariaLabel="Write approval"
      testId="write-approval-gate-banner"
      actions={
        <BusyButton
          busy={busy}
          label={writeApprovalPrimaryLabel(pathCount)}
          testId="save-all-write-approval"
          onClick={() => void approveWriteAndContinue(stage.id)}
        />
      }
    />
  );
}

function HandoffGateContent({ stage, pathCount }: { stage: StageInfo; pathCount: number }) {
  const { acknowledgeHandoff, actionBusy, jobRunning } = useApp();
  const busy = actionBusy || jobRunning;

  return (
    <ReviewGateBannerShell
      title="Review AI-generated outputs"
      lead={
        pathCount
          ? `${pathCount} output file${pathCount === 1 ? "" : "s"} from this step. Skim below if you want — or acknowledge to continue the pipeline.`
          : "This step produced AI outputs. Acknowledge when ready to continue the pipeline."
      }
      ariaLabel="Handoff review"
      testId="handoff-gate-banner"
      actions={
        <BusyButton
          busy={busy}
          label="Acknowledge & continue"
          testId="acknowledge-handoff-banner"
          onClick={() => void acknowledgeHandoff()}
        />
      }
    />
  );
}

function SfxPromptGateContent() {
  const { approveSfxPrompts, actionBusy, jobRunning } = useApp();
  const busy = actionBusy || jobRunning;

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

function FlowSelectGateContent() {
  const {
    run,
    refreshRun,
    advanceFromCheckpoint,
    showToast,
    actionBusy,
    jobRunning,
  } = useApp();
  const [submitting, setSubmitting] = useState(false);
  const busy = submitting || actionBusy || jobRunning;

  const intent = run?.flow_intent || run?.meta?.flow_intent;
  const intentValid =
    intent === "flow1" || intent === "flow2" || intent === "flow3";

  const selectFlow = async (flow: string) => {
    if (!run || busy) return;
    setSubmitting(true);
    try {
      await api(`/api/runs/${run.run_id}/flow`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flow }),
      });
      showToast(`Selected ${FLOW_LABELS[flow] || flow} — continuing pipeline.`);
      await refreshRun();
      await advanceFromCheckpoint();
    } catch (e) {
      showToast(formatApiError(e, "Flow selection"), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ReviewGateBannerShell
      title="Confirm output type (G2)"
      lead="Choose which deliverable to produce. Use your planned choice or pick a flow below."
      meta={intentValid ? `Planned: ${FLOW_LABELS[intent!] || intent}` : undefined}
      ariaLabel="Flow selection"
      testId="flow-select-gate-banner"
      actions={
        <>
          {intentValid ? (
            <BusyButton
              busy={busy}
              label={`Use planned choice (${FLOW_LABELS[intent!] || intent})`}
              testId="select-flow-use-intent-banner"
              onClick={() => void selectFlow(intent!)}
            />
          ) : null}
          <div className="flow-choice">
            {(["flow1", "flow2", "flow3"] as const).map((flow) => (
              <button
                key={flow}
                type="button"
                className={`btn sm${intent === flow ? " primary" : " ghost"}`}
                data-testid={`select-flow-${flow}`}
                disabled={busy}
                onClick={() => void selectFlow(flow)}
              >
                {FLOW_LABELS[flow]}
              </button>
            ))}
          </div>
        </>
      }
    />
  );
}

function G1VoGateContent({ missingCount }: { missingCount: number }) {
  const { advanceFromCheckpoint, actionBusy, jobRunning } = useApp();
  const busy = actionBusy || jobRunning;
  const ready = missingCount === 0;

  return (
    <ReviewGateBannerShell
      title="VO pickup (G1)"
      lead={
        ready
          ? "All pickup lines are recorded — continue to flow selection."
          : `${missingCount} pickup line${missingCount === 1 ? "" : "s"} still need recordings before you can continue.`
      }
      ariaLabel="VO pickup"
      testId="g1-vo-gate-banner"
      actions={
        <BusyButton
          busy={busy}
          label={ready ? "Continue to flow selection" : "Record lines below first"}
          testId="g1-vo-continue-banner"
          disabled={!ready}
          onClick={() => void advanceFromCheckpoint()}
        />
      }
    />
  );
}

export function StageReviewGateBanner({ spec, stage, onReviewDetail }: Props) {
  switch (spec.kind) {
    case "transcript_review":
      return <TranscriptReviewGateContent onReviewDetail={onReviewDetail} />;
    case "disfluency_review":
      return <DisfluencyReviewGateContent onReviewDetail={onReviewDetail} />;
    case "analysis_profile":
      return <AnalysisProfileGateContent />;
    case "write_approval":
      return <WriteApprovalGateContent stage={stage} pathCount={spec.pathCount ?? 0} />;
    case "handoff":
      return <HandoffGateContent stage={stage} pathCount={spec.pathCount ?? 0} />;
    case "sfx_prompt":
      return <SfxPromptGateContent />;
    case "flow_select":
      return <FlowSelectGateContent />;
    case "g1_vo":
      return <G1VoGateContent missingCount={spec.missingCount ?? 0} />;
    default:
      return null;
  }
}
