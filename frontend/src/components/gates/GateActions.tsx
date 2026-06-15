import { useEffect, useState } from "react";
import { getSfxPrompts } from "../../api/client";
import type { SfxBlockReason, StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { StageAudioActions } from "./StageAudioActions";
import { AnalysisProfileGate } from "./AnalysisProfileGate";
import { TranscriptReviewPanel } from "./TranscriptReviewPanel";
import { DisfluencyReviewPanel } from "./DisfluencyReviewPanel";
import { DisfluencyRestorePanel } from "./DisfluencyRestorePanel";
import { VoPickupPanel } from "./VoPickupPanel";
import { FlowSelectPanel } from "./FlowSelectPanel";
import { PrecleanOfferCard } from "./PrecleanOfferCard";
import { AcousticProfilePanel } from "./AcousticProfilePanel";
import { QcSummaryCard } from "./QcSummaryCard";
import { ValueFeaturesPanel } from "./ValueFeaturesPanel";
import { SfxPromptReviewPanel } from "./SfxPromptReviewPanel";
import { SfxPostListenPanel } from "./SfxPostListenPanel";
import { PlacementAdjustmentsPanel } from "./PlacementAdjustmentsPanel";
import { SfxBlockedPanel } from "./SfxBlockedPanel";
import { SonicContextPanel } from "./SonicContextPanel";
import { resolvePrecleanOffer } from "../../utils/preclean";
import { collectSfxBlockReasons } from "../../utils/sfxBlockReasons";

interface Props {
  stage: StageInfo;
}

const SONIC_CONTEXT_STAGES = new Set([
  "source_acoustic_profile",
  "sound_design_palettes",
  "sound_design_plan_flow1",
  "sound_design_plan_flow2",
]);

const MIX_INTELLIGIBILITY_STAGES = new Set([
  "mix_flow1",
  "mix_flow2",
  "master_flow1",
  "master_flow2",
]);

export function GateActions({ stage }: Props) {
  const { run, config, timeline, setPipelineSubTab } = useApp();

  const precleanOffer = run ? resolvePrecleanOffer(stage, run.meta) : null;

  if (!run) return null;

  if (
    stage.id === "topic_coverage_audit" &&
    stage.status === "locked" &&
    run.profile_gate_pending
  ) {
    return (
      <div className="gate-actions">
        <p className="hint">
          Verify the interview profile before Flow 1 extended stages — edit themes in
          Story Board, then <strong>Mark profile verified</strong>.
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
      <div className="gate-actions">
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

  if (stage.id === "mmaudio_sfx_flow1" || stage.id === "mmaudio_sfx_flow2") {
    return <SfxGatePanel stage={stage} />;
  }

  return (
    <div className="gate-actions">
      {precleanOffer ? (
        <PrecleanOfferCard stage={stage} offer={precleanOffer} />
      ) : null}

      <StageAudioActions stage={stage} />

      {stage.id === "analysis_profile" ? (
        <AnalysisProfileGate stage={stage} />
      ) : null}

      {stage.id === "g1_vo_pickup" && stage.status === "done" ? (
        <p className="hint">
          All pickup lines recorded. Optional: clean new VO files before ingest, or
          continue to flow selection.
        </p>
      ) : null}

      {stage.id === "g1_vo_pickup" && stage.status === "action_required" ? (
        <VoPickupPanel voLines={timeline?.vo_lines || []} />
      ) : null}

      {stage.id === "g2_flow_select" && stage.status === "action_required" ? (
        <FlowSelectPanel />
      ) : null}

      {stage.id === "source_acoustic_profile" ? <AcousticProfilePanel /> : null}
      {SONIC_CONTEXT_STAGES.has(stage.id) ? <SonicContextPanel /> : null}

      {stage.id === "edl_flow1" || stage.id === "assembly_preview" ? (
        <DisfluencyRestorePanel stageId={stage.id} />
      ) : null}

      {stage.id === "full_master_ranking" || stage.id === "edl_flow1" ? (
        <QcSummaryCard qcKey="narrative_qc" stageId={stage.id} />
      ) : null}

      {stage.id === "edl_flow1" || stage.id === "edl_narrative_audit" ? (
        <QcSummaryCard qcKey="edl_narrative_qc" stageId={stage.id} />
      ) : null}

      {stage.id === "podcast_show_description" ? (
        <QcSummaryCard qcKey="show_description_qc" stageId={stage.id} />
      ) : null}

      {MIX_INTELLIGIBILITY_STAGES.has(stage.id) ? (
        <QcSummaryCard qcKey="mix_intelligibility" stageId={stage.id} />
      ) : null}

      {stage.id === "mix_flow1" || stage.id === "mix_flow2" ? (
        <SfxPostListenPanel stage={stage} />
      ) : null}

      {stage.id === "content_context" &&
      (config?.value_analysis_enabled || run.meta?.qc_summaries) ? (
        <ValueFeaturesPanel />
      ) : null}

      <PlacementAdjustmentsPanel stage={stage} />
    </div>
  );
}

function SfxGatePanel({ stage }: { stage: StageInfo }) {
  const { run, selectStage } = useApp();
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
      .catch(() => {
        setBlocked(false);
        setBlockReasons([]);
      });
  }, [run, stage.id]);

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
