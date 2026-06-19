import type { GuidanceItem, StageInfo } from "../../types";
import { ActionMarker } from "./ActionMarker";
import { GuidanceActionButton } from "./GuidanceActionButton";
import { StagePrimaryAction } from "./StagePrimaryAction";
import { useApp } from "../../context/AppContext";
import { useStageProgress } from "../../hooks/useStageProgress";
import { SubstepRow } from "../pipeline/SubstepRow";

interface Props {
  stage: StageInfo;
}

function GuidanceList({
  title,
  items,
  stageId,
}: {
  title: string;
  items: GuidanceItem[];
  stageId: string;
}) {
  if (!items.length) return null;

  return (
    <div className="stage-guidance-section">
      <h3 className="stage-guidance-heading">{title}</h3>
      <ul className="stage-guidance-list">
        {items.map((item) => (
          <li
            key={item.id}
            className={`stage-guidance-item status-${item.status}`}
          >
            <ActionMarker status={item.status} />
            <span className="stage-guidance-label">{item.label}</span>
            <span className="stage-guidance-item-actions">
              <GuidanceActionButton item={item} stageId={stageId} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StageGuidancePanel({ stage }: Props) {
  const { jobRunning, run, actionBusy } = useApp();
  const { progress, substeps } = useStageProgress(stage.id);
  const guidance = stage.guidance;

  const isRunningThisStage =
    jobRunning &&
    (run?.job?.current_stage === stage.id || run?.job?.stage === stage.id);

  if (!guidance) {
    return (
      <div className="stage-guidance panel-inset">
        {isRunningThisStage ? (
          <button type="button" className="btn primary stage-primary-btn running" disabled>
            <span className="spinner-inline" aria-hidden />
            Running {stage.title}…
          </button>
        ) : (
          <StagePrimaryAction stage={stage} />
        )}
        <p className="hint">Run this stage to produce outputs. Progress appears in the activity panel.</p>
      </div>
    );
  }

  const allItems = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  const hasTodo = allItems.some((i) => i.status === "todo");

  return (
    <section className="stage-guidance panel-inset" aria-label="How to proceed">
      {isRunningThisStage || actionBusy ? (
        <button type="button" className="btn primary stage-primary-btn running" disabled>
          <span className="spinner-inline" aria-hidden />
          {actionBusy ? "Saving staged outputs…" : `Running ${stage.title}…`}
        </button>
      ) : (
        <StagePrimaryAction stage={stage} />
      )}

      {substeps.length > 0 ? (
        <ul className="stage-substep-strip" aria-label="Step checklist">
          {substeps.map((sub) => (
            <li key={`${sub.kind}:${sub.id}`}>
              <SubstepRow substep={sub} compact />
            </li>
          ))}
        </ul>
      ) : null}

      <h3 className="stage-outputs-title">
        How to proceed
        {hasTodo ? (
          <span className="stage-guidance-badge muted">Details below</span>
        ) : progress?.fullyComplete ? (
          <span className="stage-guidance-badge muted">Complete</span>
        ) : null}
      </h3>
      <p className="hint stage-guidance-phase">
        {guidance.phase_label} phase
        {guidance.unlocks ? (
          <>
            {" "}
            · Unlocks: <strong>{guidance.unlocks}</strong>
          </>
        ) : null}
      </p>

      <GuidanceList title="Before you start" items={guidance.prerequisites || []} stageId={stage.id} />
      <GuidanceList title="Step checklist" items={guidance.actions || []} stageId={stage.id} />

      {(guidance.artifact_checks || []).length > 0 ? (
        <div className="stage-guidance-section">
          <h3 className="stage-guidance-heading">Expected files</h3>
          <ul className="stage-guidance-list compact">
            {(guidance.artifact_checks || []).map((check) => (
              <li key={check.path} className={`stage-guidance-item status-${check.status}`}>
                <ActionMarker status={check.status} />
                <code className="artifact-path">{check.path}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
