import type { GuidanceItem, StageInfo } from "../../types";
import { ActionMarker } from "./ActionMarker";
import { GuidanceActionButton } from "./GuidanceActionButton";
import { findNextRunnableStage } from "../../utils/preclean";
import { useApp } from "../../context/AppContext";

interface Props {
  stage: StageInfo;
  stepNumber?: number | null;
}

function GuidanceList({
  title,
  items,
  stage,
  prereqsMet,
}: {
  title: string;
  items: GuidanceItem[];
  stage: StageInfo;
  stepNumber?: number | null;
  prereqsMet?: boolean;
}) {
  const { run } = useApp();
  if (!items.length) return null;

  const nextRunnable = run ? findNextRunnableStage(run.stages) : null;
  const canRunHere =
    prereqsMet &&
    nextRunnable?.id === stage.id &&
    stage.status === "pending";

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
              {item.kind === "run" && item.status === "todo" && canRunHere ? (
                <span className="hint sm">Use Run in the status bar above</span>
              ) : (
                <GuidanceActionButton item={item} />
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StageGuidancePanel({ stage, stepNumber }: Props) {
  const guidance = stage.guidance;
  if (!guidance) {
    return (
      <div className="stage-guidance panel-inset">
        <p className="hint">Run this stage to produce outputs. Progress appears in the activity panel.</p>
      </div>
    );
  }

  const allItems = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  const hasTodo = allItems.some((i) => i.status === "todo");
  const prereqsMet = !(guidance.prerequisites || []).some((i) => i.status === "todo");

  return (
    <section className="stage-guidance panel-inset" aria-label="How to proceed">
      <h3 className="stage-outputs-title">
        How to proceed
        {hasTodo ? (
          <span className="stage-guidance-badge muted">Action required</span>
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

      <GuidanceList
        title="Before you start"
        items={guidance.prerequisites || []}
        stage={stage}
        stepNumber={stepNumber}
        prereqsMet={prereqsMet}
      />
      <GuidanceList
        title="Your next actions"
        items={guidance.actions || []}
        stage={stage}
        stepNumber={stepNumber}
        prereqsMet={prereqsMet}
      />

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
