import type { StageInfo, StageStep } from "../../types";
import { GateActions } from "../gates/GateActions";
import { PrecleanOfferCard } from "../gates/PrecleanOfferCard";
import { HandoffPanel } from "./HandoffPanel";
import { StageReuseSection } from "../guidance/StageReuseSection";
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
      return <StageReuseSection stage={stage} />;

    case "run":
      return (
        <p className="hint sm">
          {step.status === "active"
            ? "Job running — watch the activity log on the right."
            : "Click Run above when ready."}
        </p>
      );

    case "write_approval":
      return (
        <>
          <WriteApprovalPanel stage={stage} />
          {step.embed === "transcript_dock" ? (
            <section className="stage-transcript-dock">
              <TranscriptDockViewer />
            </section>
          ) : null}
        </>
      );

    case "handoff":
      return (
        <>
          <HandoffPanel />
          <StageOutputsPanel stage={stage} />
        </>
      );

    case "preclean":
      return precleanOffer ? (
        <PrecleanOfferCard stage={stage} offer={precleanOffer} />
      ) : null;

    case "gate":
      return <GateActions stage={stage} />;

    case "embed_transcript_dock":
      return (
        <>
          <TranscriptReviewPanel />
          <section className="stage-transcript-dock">
            <TranscriptDockViewer />
          </section>
        </>
      );

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
