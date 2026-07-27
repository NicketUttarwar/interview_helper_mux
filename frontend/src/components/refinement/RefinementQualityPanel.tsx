import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { useRefinementSummary } from "../../hooks/useRefinementSummary";
import { runHasRefinementSignal } from "../../utils/refinementStage";
import { refinementClassLabel } from "../../utils/refinementLabels";
import type { RefinementRecomposeDoc } from "../../types";
import { RefinementChampionPanel } from "./RefinementChampionPanel";
import { RefinementEvidencePanel } from "./RefinementEvidencePanel";
import { RefinementOutcomeTrajectory } from "./RefinementOutcomeTrajectory";
import { RefinementSkipReasons } from "./RefinementSkipReasons";
import { RefinementBibleMiniView } from "./RefinementBibleMiniView";
import { RefinementListenerContract } from "./RefinementListenerContract";
import { RefinementExplainThisRun } from "./RefinementExplainThisRun";
import { RefinementChaosGalleryLink } from "./RefinementChaosGalleryLink";
import { RefinementPreviewAnnotations } from "./RefinementPreviewAnnotations";

/**
 * Quality/honesty surfaces for the Refinement Pass system — source-honesty banner, champion
 * compare, evidence packet links, cascade preview, listener outcome trajectory, skip reasons,
 * and a lightweight story bible. Renders nothing when the run has no refinement signal at all.
 */
const RECOMPOSE_PATH = "understanding/gap_framing_recompose.json";

export function RefinementQualityPanel() {
  const { run, runId, openArtifactInEditor } = useApp();
  const summary = useRefinementSummary(runId, run);
  const [lastRecompose, setLastRecompose] = useState<RefinementRecomposeDoc | null>(null);

  const hasGapVoChampion = Boolean(summary.champion?.gap_vo);

  useEffect(() => {
    if (!runId || !hasGapVoChampion) {
      setLastRecompose(null);
      return;
    }
    let cancelled = false;
    void api<RefinementRecomposeDoc>(
      `/api/runs/${runId}/artifact?path=${encodeURIComponent(RECOMPOSE_PATH)}`,
    )
      .then((doc) => {
        if (!cancelled) setLastRecompose(doc || null);
      })
      .catch(() => {
        if (!cancelled) setLastRecompose(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, hasGapVoChampion]);

  if (!run || !runHasRefinementSignal(run)) return null;

  const agenda = summary.agenda;
  const eligible = agenda?.eligible_classes || [];
  const tapeCharacter = agenda?.tape_character || [];

  return (
    <section className="refinement-quality-panel panel-inset" aria-label="Refinement pass quality">
      <h4 className="refinement-quality-title">Refinement pass — quality</h4>

      {agenda ? (
        <p className="refinement-honesty-banner hint sm" data-testid="refinement-honesty-banner">
          {tapeCharacter.length ? (
            <>
              This tape reads as <strong>{tapeCharacter.join(", ")}</strong>.{" "}
            </>
          ) : null}
          {eligible.length ? (
            <>
              Pass 2 focuses on: <strong>{eligible.map(refinementClassLabel).join(", ")}</strong>.
            </>
          ) : (
            <>No Pass 2 classes are eligible for this tape — it stays a single clean pass.</>
          )}
        </p>
      ) : null}

      {agenda?.north_star_notes ? (
        <p className="hint sm refinement-north-star-note">{agenda.north_star_notes}</p>
      ) : null}

      <RefinementChampionPanel
        champion={summary.champion}
        lastRecomposeAccept={lastRecompose?.accept}
      />
      <RefinementEvidencePanel
        evidencePackets={summary.evidence_packets}
        cascade={summary.cascade}
        onOpen={openArtifactInEditor}
      />
      <RefinementOutcomeTrajectory trajectory={summary.listener_outcome_trajectory} />
      <RefinementSkipReasons plan={summary.plan} />
      <RefinementBibleMiniView bible={summary.bible} />
      <RefinementPreviewAnnotations annotations={summary.preview_annotations} />
      <RefinementListenerContract />
      <RefinementExplainThisRun />
      <RefinementChaosGalleryLink />
    </section>
  );
}
