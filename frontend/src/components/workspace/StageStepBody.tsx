import type { StageInfo, StageStep } from "../../types";
import { GateActions } from "../gates/GateActions";
import { PrecleanOfferCard } from "../gates/PrecleanOfferCard";
import { HandoffPanel } from "./HandoffPanel";
import { WriteApprovalPanel } from "../guidance/WriteApprovalPanel";
import { TranscriptDockViewer } from "./TranscriptDockViewer";
import { StoryBoardPanel } from "./StoryBoardPanel";
import { NlePanel } from "./NlePanel";
import { AcousticProfilePanel } from "../gates/AcousticProfilePanel";
import { InterviewSpinePanel } from "./InterviewSpinePanel";
import { SonicContextPanel } from "../gates/SonicContextPanel";
import { CoherenceRisksPanel } from "./CoherenceRisksPanel";
import { PreviewListenPromo } from "../guidance/PreviewListenPromo";
import { SfxPostListenPanel } from "../gates/SfxPostListenPanel";
import { PlacementAdjustmentsPanel } from "../gates/PlacementAdjustmentsPanel";
import { DeliverableCard } from "./DeliverableCard";
import { StageOutputsPanel } from "./StageOutputsPanel";
import { LlmCallsPanel } from "./LlmCallsPanel";
import { VolleyMemoryPanel } from "./VolleyMemoryPanel";
import { TranscriptReviewPanel } from "../gates/TranscriptReviewPanel";
import { DisfluencyReviewPanel } from "../gates/DisfluencyReviewPanel";
import { AnalysisProfileGate } from "../gates/AnalysisProfileGate";
import { VoPickupPanel } from "../gates/VoPickupPanel";
import { FlowSelectPanel } from "../gates/FlowSelectPanel";
import { SfxPromptReviewPanel } from "../gates/SfxPromptReviewPanel";
import { useApp } from "../../context/AppContext";
import { resolvePrecleanOffer } from "../../utils/preclean";

interface Props {
  step: StageStep;
  stage: StageInfo;
}

export function StageStepBody({ step, stage }: Props) {
  const { run, timeline } = useApp();
  const precleanOffer = run ? resolvePrecleanOffer(stage, run.meta) : null;

  if (
    step.id === "complete_g0" &&
    stage.id === "transcript_review" &&
    stage.status === "action_required"
  ) {
    return (
      <div className="tr-complete-step-body">
        <p className="hint">
          Use <strong>Accept all &amp; proceed</strong> in the banner above to sign off without
          reviewing every clip.
        </p>
      </div>
    );
  }

  if (
    step.id === "complete_g05" &&
    stage.id === "disfluency_review" &&
    stage.status === "action_required"
  ) {
    return (
      <div className="tr-complete-step-body">
        <p className="hint">
          Use <strong>Accept all &amp; proceed</strong> in the banner above to confirm all filler
          clips and continue without reviewing each one.
        </p>
      </div>
    );
  }

  if (
    step.id === "verify_profile" &&
    stage.id === "analysis_profile" &&
    stage.status === "action_required"
  ) {
    return (
      <div className="tr-complete-step-body">
        <p className="hint">
          Use <strong>Approve profile &amp; proceed</strong> in the banner above to verify the AI
          story profile and unlock later stages.
        </p>
      </div>
    );
  }

  if (step.kind === "write_approval") {
    return (
      <div className="stage-decision-panel" data-testid="stage-write-approval-decision">
        <p className="hint sm">
          Use <strong>Save all files &amp; continue</strong> in the banner above to approve staged
          outputs without opening each file.
        </p>
        <WriteApprovalPanel stage={stage} />
        {step.embed === "transcript_dock" ? (
          <section className="stage-transcript-dock">
            <TranscriptDockViewer />
          </section>
        ) : null}
      </div>
    );
  }

  if (step.kind === "handoff") {
    return (
      <>
        <p className="hint sm">
          Use <strong>Acknowledge &amp; continue</strong> in the banner above to sign off on AI
          outputs without opening each file.
        </p>
        <HandoffPanel />
        <StageOutputsPanel stage={stage} />
      </>
    );
  }

  switch (step.kind) {
    case "info":
      return stage.guidance?.prerequisites?.length ? (
        <ul className="stage-step-prereq-list">
          {(stage.guidance.prerequisites || []).map((p) => (
            <li key={p.id} className={`prereq-${p.status}`}>
              {p.label}
            </li>
          ))}
        </ul>
      ) : null;

    case "reuse":
      return (
        <p className="hint sm" data-testid="stage-reuse-step-hint">
          Prior-run reuse options are shown at the top of this panel. Accept reuse there to skip
          re-running this step, or choose <strong>Run fresh</strong>.
        </p>
      );

    case "run":
      return (
        <p className="hint sm">
          {step.status === "active"
            ? "Job running — watch the activity log on the right."
            : "Click Run above when ready."}
        </p>
      );


    case "preclean":
      return precleanOffer ? (
        <PrecleanOfferCard stage={stage} offer={precleanOffer} />
      ) : null;

    case "gate":
      return <GateActions stage={stage} />;

    case "embed_transcript_dock":
      return <TranscriptReviewPanel />;

    case "embed_story_board":
      return (
        <>
          <StoryBoardPanel />
          <AnalysisProfileGate stage={stage} />
        </>
      );

    case "embed_timeline":
      return <NlePanel />;

    case "listen":
      return (
        <>
          <PreviewListenPromo />
          <StageOutputsPanel stage={stage} />
        </>
      );

    case "embed_post_listen":
      return <SfxPostListenPanel stage={stage} />;

    case "done":
      return (
        <>
          <StageOutputsPanel stage={stage} />
        </>
      );

    case "locked":
      return (
        <p className="hint">
          Complete the blocking stage first, then return here.
        </p>
      );

    case "embed_debug":
      return (
        <details className="stage-step-debug">
          <summary>Engineering debug</summary>
          <LlmCallsPanel />
          <VolleyMemoryPanel />
        </details>
      );

    default:
      break;
  }

  switch (step.embed) {
    case "transcript_dock":
      return <TranscriptDockViewer />;
    case "acoustic_profile":
      return <AcousticProfilePanel />;
    case "interview_spine":
      return <InterviewSpinePanel />;
    case "sonic_context":
      return <SonicContextPanel />;
    case "coherence_risks":
      return <CoherenceRisksPanel />;
    case "timeline":
      return <NlePanel />;
    case "post_listen":
      return <SfxPostListenPanel stage={stage} />;
    case "placement_qa":
      return <PlacementAdjustmentsPanel stage={stage} />;
    case "deliverable":
      return <DeliverableCard />;
    case "transcript_review":
      return <TranscriptReviewPanel />;
    case "disfluency_review":
      return <DisfluencyReviewPanel />;
    case "analysis_profile":
      return <AnalysisProfileGate stage={stage} />;
    case "vo_pickup":
      return <VoPickupPanel voLines={timeline?.vo_lines || []} />;
    case "flow_select":
      return <FlowSelectPanel />;
    case "sfx_prompt_review":
      return <SfxPromptReviewPanel stage={stage} />;
    case "debug":
      return (
        <details className="stage-step-debug">
          <summary>Engineering debug</summary>
          <LlmCallsPanel />
          <VolleyMemoryPanel />
        </details>
      );
    default:
      if (step.kind === "gate") return <GateActions stage={stage} />;
      return step.status === "done" ? <StageOutputsPanel stage={stage} /> : null;
  }
}
