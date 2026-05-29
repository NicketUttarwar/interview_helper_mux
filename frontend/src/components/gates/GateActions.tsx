import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { StageInfo } from "../../types";
import { useApp } from "../../context/AppContext";
import { StageAudioActions } from "./StageAudioActions";
import { AnalysisProfileGate } from "./AnalysisProfileGate";
import { TranscriptReviewPanel } from "./TranscriptReviewPanel";
import { VoPickupPanel } from "./VoPickupPanel";
import { FlowSelectPanel } from "./FlowSelectPanel";
import { PrecleanOfferCard } from "./PrecleanOfferCard";
import { AcousticProfilePanel } from "./AcousticProfilePanel";
import { QcSummaryCard } from "./QcSummaryCard";
import { ValueFeaturesPanel } from "./ValueFeaturesPanel";
import { ElevenLabsPromptReviewPanel } from "./ElevenLabsPromptReviewPanel";
import { ElevenLabsPostListenPanel } from "./ElevenLabsPostListenPanel";
import { ElevenLabsBlockedPanel } from "./ElevenLabsBlockedPanel";
import { resolvePrecleanOffer } from "../../utils/preclean";

interface Props {
  stage: StageInfo;
}

export function GateActions({ stage }: Props) {
  const { run, config, timeline } = useApp();

  if (!run) return null;

  const precleanOffer = resolvePrecleanOffer(stage);

  if (
    stage.id === "topic_coverage_audit" &&
    stage.status === "locked" &&
    run.profile_gate_pending
  ) {
    return (
      <div className="gate-actions">
        <p className="hint">
          <strong>Profile gate:</strong> verify the interview profile before Flow 1
          extended analysis. Open <strong>Interview profile</strong> in the stage list,
          edit themes and style, then click <strong>Mark profile verified</strong>.
        </p>
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

  if (stage.id === "elevenlabs_prompt_craft") {
    return (
      <div className="gate-actions">
        <ElevenLabsPromptReviewPanel stage={stage} />
        <ElevenLabsPostListenPanel stage={stage} />
      </div>
    );
  }

  if (stage.id === "elevenlabs_sfx_flow1" || stage.id === "elevenlabs_sfx_flow2") {
    return <SfxGatePanel stage={stage} />;
  }

  return (
    <div className="gate-actions">
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

      {stage.id === "full_master_ranking" || stage.id === "edl_flow1" ? (
        <QcSummaryCard qcKey="narrative_qc" />
      ) : null}

      {stage.id === "podcast_show_description" ? (
        <QcSummaryCard qcKey="show_description_qc" />
      ) : null}

      {stage.id === "content_context" &&
      (config?.value_analysis_enabled || run.meta?.qc_summaries) ? (
        <ValueFeaturesPanel />
      ) : null}

      {precleanOffer ? (
        <PrecleanOfferCard stage={stage} offer={precleanOffer} />
      ) : null}
    </div>
  );
}

function SfxGatePanel({ stage }: { stage: StageInfo }) {
  const { run, selectStage } = useApp();
  const [blocked, setBlocked] = useState<boolean | null>(null);

  useEffect(() => {
    if (!run) return;
    void api<{ review_required?: boolean; can_generate?: boolean }>(
      `/api/runs/${run.run_id}/elevenlabs-prompts`,
    )
      .then((review) => {
        setBlocked(
          Boolean(review?.review_required && review?.can_generate === false),
        );
      })
      .catch(() => setBlocked(false));
  }, [run, stage.id]);

  if (blocked === null) return <div className="gate-actions" />;

  if (blocked) {
    return (
      <div className="gate-actions">
        <ElevenLabsBlockedPanel
          onOpen={() => void selectStage("elevenlabs_prompt_craft")}
        />
      </div>
    );
  }

  const offer = resolvePrecleanOffer(stage);
  return (
    <div className="gate-actions">
      <ElevenLabsPostListenPanel stage={stage} />
      {offer ? <PrecleanOfferCard stage={stage} offer={offer} /> : null}
    </div>
  );
}
