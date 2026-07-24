import type { StageInfo, StageStep } from "../../types";
import { GateActions } from "../gates/GateActions";
import { TranscriptDockViewer } from "./TranscriptDockViewer";
import { NlePanel } from "./NlePanel";
import { AcousticProfilePanel } from "../gates/AcousticProfilePanel";
import { InterviewSpinePanel } from "./InterviewSpinePanel";
import { SonicContextPanel } from "../gates/SonicContextPanel";
import { SpeakerVolleyTimelinePanel } from "../gates/SpeakerVolleyTimelinePanel";
import { LlmVolleyReviewPanel } from "../gates/LlmVolleyReviewPanel";
import { CoherenceRisksPanel } from "./CoherenceRisksPanel";
import { PreviewListenPromo } from "../guidance/PreviewListenPromo";
import { SfxPostListenPanel } from "../gates/SfxPostListenPanel";
import { PlacementAdjustmentsPanel } from "../gates/PlacementAdjustmentsPanel";
import { DeliverableCard } from "./DeliverableCard";
import { StageOutputsPanel } from "./StageOutputsPanel";
import { TranscriptReviewPanel } from "../gates/TranscriptReviewPanel";
import { VoPickupPanel } from "../gates/VoPickupPanel";
import { PreviewPickupPanel } from "../gates/PreviewPickupPanel";
import { SfxPromptReviewPanel } from "../gates/SfxPromptReviewPanel";
import { GapFramingGatePanel } from "../gates/GapFramingGatePanel";
import { GapFramingScriptPanel } from "../gates/GapFramingScriptPanel";
import { ImpactBlockPreview } from "../gates/ImpactBlockPreview";
import { VoiceReferencePanel } from "../gates/VoiceReferencePanel";
import { GapDeliveryPanel } from "../gates/GapDeliveryPanel";
import { PickupSpeakerPanel } from "../gates/PickupSpeakerPanel";
import { useApp } from "../../context/AppContext";
import { resolvePrecleanOffer } from "../../utils/preclean";

interface Props {
  step: StageStep;
  stage: StageInfo;
}

export function StageStepBody({ step, stage }: Props) {
  const { run, timeline } = useApp();
  const precleanOffer = run ? resolvePrecleanOffer(stage, run.meta) : null;

  if (step.kind === "progress" || step.id === "auto_resolving") {
    return (
      <p className="hint sm" data-testid="stage-auto-resolving">
        Automatic repairs and validation are running — watch the activity log.
      </p>
    );
  }

  if (step.id === "llm_gate") {
    const gateMsg = run?.job?.message;
    const lintFromGuidance =
      stage?.guidance?.prerequisites
        ?.filter((p) => p.id === "llm_lint")
        .map((p) => p.label.replace(/^Latest attempt lint:\s*/i, "")) || [];
    const lintLines = lintFromGuidance;
    const copyLint = () => {
      const text = [gateMsg, ...lintLines].filter(Boolean).join("\n");
      if (text) void navigator.clipboard.writeText(text);
    };
    return (
      <div className="stage-decision-panel" data-testid="stage-llm-gate-decision">
        {gateMsg ? (
          <p className="hint sm stage-llm-gate-message">{gateMsg}</p>
        ) : (
          <p className="hint sm">
            The automated quality gate rejected this stage. Review Engineering debug below, then use{" "}
            <strong>Re-run</strong> or <strong>Discard staged attempt</strong> in the step footer.
          </p>
        )}
        {lintLines.length ? (
          <div className="stage-lint-failure-banner panel-inset">
            <div className="stage-lint-failure-head">
              <strong>Deterministic lint failures</strong>
              <button type="button" className="btn ghost sm" onClick={copyLint}>
                Copy errors
              </button>
            </div>
            <ul className="stage-lint-error-list">
              {lintLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }

  switch (step.kind) {
    case "info":
      return stage.guidance?.prerequisites?.length ? (
        <ul className="stage-step-prereq-list">
          {(stage.guidance.prerequisites || []).map((p) => (
            <li
              key={p.id}
              className={`prereq-${p.status}${p.category === "stage_health" ? " prereq-health" : ""}`}
            >
              {p.label}
              {p.category === "stage_health" && p.status === "todo" ? (
                <span className="hint sm"> — discard staged outputs if budget exhausted, then re-run</span>
              ) : null}
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
      return (
        <p className="hint sm">
          {precleanOffer
            ? precleanOffer.scope === "g1_vo_pickup"
              ? "Optional pickup cleaning — use the buttons below to run or skip."
              : "Optional source cleaning — use the buttons below to run or skip before ingest."
            : "Pre-clean step complete or not applicable."}
        </p>
      );

    case "gate":
      return <GateActions stage={stage} />;

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
      return <StageOutputsPanel stage={stage} />;

    case "locked":
      return (
        <p className="hint">
          Complete the blocking stage first, then return here.
        </p>
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
      return (
        <>
          <SonicContextPanel />
          <SpeakerVolleyTimelinePanel />
        </>
      );
    case "coherence_risks":
      return <CoherenceRisksPanel />;
    case "timeline":
      return (
        <>
          <NlePanel />
          <SpeakerVolleyTimelinePanel />
        </>
      );
    case "post_listen":
      return <SfxPostListenPanel stage={stage} />;
    case "placement_qa":
      return <PlacementAdjustmentsPanel stage={stage} />;
    case "deliverable":
      return (
        <>
          <DeliverableCard />
          <LlmVolleyReviewPanel />
        </>
      );
    case "transcript_review":
      return <TranscriptReviewPanel />;
    case "gap_framing_script":
      return <GapFramingScriptPanel stage={stage} />;
    case "impact_preview":
      return <ImpactBlockPreview />;
    case "gap_framing":
      return <GapFramingGatePanel stage={stage} />;
    case "voice_reference":
      return <VoiceReferencePanel stage={stage} />;
    case "gap_delivery":
      return <GapDeliveryPanel stage={stage} />;
    case "pickup_speaker":
      return <PickupSpeakerPanel stage={stage} />;
    case "vo_pickup":
      return <VoPickupPanel voLines={timeline?.vo_lines || []} />;
    case "preview_pickup":
      return <PreviewPickupPanel voLines={timeline?.vo_lines || []} />;
    case "sfx_prompt_review":
      return <SfxPromptReviewPanel stage={stage} />;
    default:
      if (step.kind === "gate") return <GateActions stage={stage} />;
      return step.status === "done" ? <StageOutputsPanel stage={stage} /> : null;
  }
}
