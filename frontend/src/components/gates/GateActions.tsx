import { useEffect, useState, type ReactNode } from "react";
import { getSfxPrompts } from "../../api/client";
import type { SfxBlockReason, StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { StageAudioActions } from "./StageAudioActions";
import { AnalysisProfileGate } from "./AnalysisProfileGate";
import { TranscriptReviewPanel } from "./TranscriptReviewPanel";
import { DisfluencyReviewPanel } from "./DisfluencyReviewPanel";
import { DisfluencyRestorePanel } from "./DisfluencyRestorePanel";
import { VoPickupPanel } from "./VoPickupPanel";
import { PreviewPickupPanel } from "./PreviewPickupPanel";
import { ConversationStudioPanel } from "./ConversationStudioPanel";
import { PickupSpeakerPanel } from "./PickupSpeakerPanel";
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
import { collectSfxBlockReasons } from "../../utils/sfxBlockReasons";
import { resolvePrecleanOffer } from "../../utils/preclean";
import { isStageHidden } from "../../utils/stageVisibility";
import { GatePanelShell } from "../pipeline/GatePanelShell";

interface Props {
  stage: StageInfo;
}

const SONIC_CONTEXT_STAGES = new Set([
  "source_acoustic_profile",
  "sound_design_palettes",
  "sound_design_plan",
]);

const MIX_INTELLIGIBILITY_STAGES = new Set(["mix", "master_finalize"]);

function wrapDoneGate(stage: StageInfo, children: ReactNode, title?: string) {
  if (stage.status !== "done") return children;
  return (
    <GatePanelShell complete title={title ?? `${stage.title} complete`}>
      {children}
    </GatePanelShell>
  );
}

export function GateActions({ stage }: Props) {
  const { run, config, timeline, setPipelineSubTab } = useApp();

  if (!run) return null;
  if (isStageHidden(stage)) return null;

  if (
    stage.id === "topic_coverage_audit" &&
    stage.status === "locked" &&
    run.profile_gate_pending
  ) {
    return (
      <div className="gate-actions">
        <p className="hint">
          Verify the interview profile before delivery stages — edit themes in Story Board,
          then <strong>Mark profile verified</strong>.
        </p>
        <div className="flow-choice">
          <button
            type="button"
            className="btn primary sm"
            onClick={() => setPipelineSubTab("story")}
          >
            Open Story Board
          </button>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setPipelineSubTab("profile")}
          >
            Open profile
          </button>
        </div>
      </div>
    );
  }

  if (stage.id === "transcript_review" && stage.status === "action_required") {
    return (
      <div className="gate-actions attention-required">
        <TranscriptReviewPanel />
      </div>
    );
  }

  if (stage.id === "disfluency_review" && stage.status === "action_required") {
    return (
      <div className="gate-actions">
        <DisfluencyReviewPanel />
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
          <StageAudioActions stage={stage} />

          {stage.id === "analysis_profile" ? <AnalysisProfileGate stage={stage} /> : null}

          {stage.id === "missing_framing" && stage.status === "action_required" ? (
            <PickupSpeakerPanel stage={stage} />
          ) : null}

          {stage.id === "optimal_questions" && stage.status === "done" ? (
            <ConversationStudioPanel />
          ) : null}

          {stage.id === "g1_vo_pickup" && stage.status === "done" ? (
            <p className="hint">
              All pickup lines recorded. Optional: clean new VO files before ingest, or continue
              to delivery.
            </p>
          ) : null}

          {stage.id === "g1_vo_pickup" && stage.status === "action_required" ? (
            <VoPickupPanel voLines={timeline?.vo_lines || []} />
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

          {stage.id === "edl" || stage.id === "assembly_preview" ? (
            <DisfluencyRestorePanel stageId={stage.id} />
          ) : null}

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
