import { useEffect, useState, type ReactNode } from "react";
import { getSfxPrompts } from "../../api/client";
import type { SfxBlockReason, StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { StageAudioActions } from "./StageAudioActions";
import { TranscriptReviewPanel } from "./TranscriptReviewPanel";
import { VoPickupPanel } from "./VoPickupPanel";
import { PreviewPickupPanel } from "./PreviewPickupPanel";
import { ConversationStudioPanel } from "./ConversationStudioPanel";
import { PickupSpeakerPanel } from "./PickupSpeakerPanel";
import { GapFramingGatePanel } from "./GapFramingGatePanel";
import { GapFramingScriptPanel } from "./GapFramingScriptPanel";
import { ImpactBlockPreview } from "./ImpactBlockPreview";
import { VoiceReferencePanel } from "./VoiceReferencePanel";
import { GapDeliveryPanel } from "./GapDeliveryPanel";
import { PrecleanOfferCard } from "./PrecleanOfferCard";
import { AcousticProfilePanel } from "./AcousticProfilePanel";
import { InterviewSpinePanel } from "../workspace/InterviewSpinePanel";
import { QcSummaryCard } from "./QcSummaryCard";
import { ValueFeaturesPanel } from "./ValueFeaturesPanel";
import { SfxPromptReviewPanel } from "./SfxPromptReviewPanel";
import { SfxPostListenPanel } from "./SfxPostListenPanel";
import { PlacementAdjustmentsPanel } from "./PlacementAdjustmentsPanel";
import { SfxBlockedPanel } from "./SfxBlockedPanel";
import { SonicContextPanel } from "./SonicContextPanel";
import { AudioProbesPanel } from "./AudioProbesPanel";
import { collectSfxBlockReasons } from "../../utils/sfxBlockReasons";
import { resolvePrecleanOffer } from "../../utils/preclean";
import { isStageHidden } from "../../utils/stageVisibility";
import { isRefinementPassStage } from "../../utils/refinementStage";
import { GatePanelShell } from "../pipeline/GatePanelShell";
import { RefinementQualityPanel } from "../refinement/RefinementQualityPanel";

interface Props {
  stage: StageInfo;
}

const SONIC_CONTEXT_STAGES = new Set([
  "source_acoustic_profile",
  "sound_design_palettes",
  "sound_design_plan",
]);

const AUDIO_PROBES_STAGES = new Set([
  "audio_probe_build",
  "vernacular_segment_sanitize",
]);

const MIX_INTELLIGIBILITY_STAGES = new Set(["mix", "master_finalize"]);

/** Stages where the Refinement Pass quality panel (agenda/champion/evidence/etc.) is relevant. */
function showsRefinementQuality(stage: StageInfo): boolean {
  return (
    isRefinementPassStage(stage) ||
    stage.id === "gap_framing_compose" ||
    stage.id === "optimal_questions"
  );
}

function wrapDoneGate(stage: StageInfo, children: ReactNode, title?: string) {
  if (stage.status !== "done") return children;
  return (
    <GatePanelShell complete title={title ?? `${stage.title} complete`}>
      {children}
    </GatePanelShell>
  );
}

/** v2 operator gates: G0 transcript review, G1 VO pickup, NLE timeline, and stage-specific panels. */
export function GateActions({ stage }: Props) {
  const { run, config, timeline } = useApp();

  if (!run) return null;
  if (isStageHidden(stage)) return null;

  if (stage.id === "transcript_review" && stage.status === "action_required") {
    return (
      <div className="gate-actions attention-required">
        <TranscriptReviewPanel />
      </div>
    );
  }

  if (stage.id === "sfx_prompt_craft") {
    return (
      <div className="gate-actions">
        <SfxPromptReviewPanel stage={stage} />
        <SfxPostListenPanel stage={stage} />
      </div>
    );
  }

  if (stage.id === "mmaudio_sfx") {
    return <SfxGatePanel stage={stage} />;
  }

  return wrapDoneGate(
    stage,
    (
      <div className="gate-actions">
        <div className="attention-required-wrap">
          {showsRefinementQuality(stage) ? <RefinementQualityPanel /> : null}
          <StageAudioActions stage={stage} />

          {stage.id === "missing_framing" && stage.status === "action_required" ? (
            <>
              <GapFramingGatePanel stage={stage} />
              <PickupSpeakerPanel stage={stage} />
              <VoiceReferencePanel stage={stage} />
              <GapDeliveryPanel stage={stage} />
            </>
          ) : null}

          {(stage.id === "gap_framing_compose" || stage.id === "optimal_questions") &&
          stage.status === "done" ? (
            <>
              <GapFramingScriptPanel stage={stage} />
              <ConversationStudioPanel />
            </>
          ) : null}

          {stage.id === "g1_vo_pickup" && stage.status === "action_required" ? (
            <>
              <GapFramingScriptPanel stage={stage} />
              <ImpactBlockPreview />
              <VoPickupPanel voLines={timeline?.vo_lines || []} />
            </>
          ) : null}

          {stage.id === "g1_5_preview_pickup" && stage.status === "action_required" ? (
            <PreviewPickupPanel voLines={timeline?.vo_lines || []} />
          ) : null}

          {(stage.id === "assembly_preview" || stage.id === "mmaudio_sfx") &&
          (run.g1_5_preview_pickup_pending || []).length > 0 ? (
            <PreviewPickupPanel voLines={timeline?.vo_lines || []} />
          ) : null}

          {stage.id === "source_acoustic_profile" ? <AcousticProfilePanel /> : null}
          {stage.id === "interview_spine_build" ? <InterviewSpinePanel /> : null}
          {SONIC_CONTEXT_STAGES.has(stage.id) ? <SonicContextPanel /> : null}
          {AUDIO_PROBES_STAGES.has(stage.id) ? <AudioProbesPanel /> : null}

          {run.journey?.phase === "ship" ? (
            <>
              {stage.id === "full_master_ranking" || stage.id === "edl" ? (
                <QcSummaryCard qcKey="narrative_qc" stageId={stage.id} />
              ) : null}

              {stage.id === "edl" || stage.id === "edl_narrative_audit" ? (
                <QcSummaryCard qcKey="edl_narrative_qc" stageId={stage.id} />
              ) : null}

              {stage.id === "master_finalize" ? (
                <QcSummaryCard qcKey="show_notes_qc" stageId={stage.id} />
              ) : null}

              {MIX_INTELLIGIBILITY_STAGES.has(stage.id) ? (
                <QcSummaryCard qcKey="mix_intelligibility" stageId={stage.id} />
              ) : null}
            </>
          ) : null}

          {stage.id === "content_context" &&
          (config?.value_analysis_enabled || run.meta?.qc_summaries) ? (
            <ValueFeaturesPanel />
          ) : null}

          <PlacementAdjustmentsPanel stage={stage} />
        </div>
      </div>
    ),
  );
}

function SfxGatePanel({ stage }: { stage: StageInfo }) {
  const { run, selectStage, showToast } = useApp();
  const [blocked, setBlocked] = useState<boolean | null>(null);
  const [blockReasons, setBlockReasons] = useState<SfxBlockReason[]>([]);

  useEffect(() => {
    if (!run) return;
    void getSfxPrompts(run.run_id)
      .then((review) => {
        const reasons = collectSfxBlockReasons(review);
        setBlocked(Boolean(review?.review_required && review?.can_generate === false));
        setBlockReasons(reasons);
      })
      .catch((e) => {
        showToast(e instanceof Error ? e.message : "Could not load SFX prompts", "error");
        setBlocked(false);
        setBlockReasons([]);
      });
  }, [run, stage.id, showToast]);

  if (blocked === null) {
    return (
      <div className="gate-actions">
        <p className="hint gate-loading">
          <span className="spinner-inline" aria-hidden /> Checking MMAudio approval…
        </p>
      </div>
    );
  }

  if (blocked) {
    return (
      <div className="gate-actions">
        <SfxBlockedPanel
          reasons={blockReasons}
          onOpen={() => void selectStage("sfx_prompt_craft")}
        />
      </div>
    );
  }

  const offer = resolvePrecleanOffer(stage, run?.meta);
  return (
    <div className="gate-actions">
      <SfxPostListenPanel stage={stage} />
      <PlacementAdjustmentsPanel stage={stage} />
      {offer ? <PrecleanOfferCard stage={stage} offer={offer} /> : null}
    </div>
  );
}
