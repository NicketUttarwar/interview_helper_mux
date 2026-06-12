import type { GuidanceItem, StageInfo } from "../../types";
import { ActionMarker } from "./ActionMarker";
import { GuidanceActionButton } from "./GuidanceActionButton";
import { StagePrimaryAction } from "./StagePrimaryAction";
import { useApp } from "../../context/AppContext";

interface Props {
  stage: StageInfo;
}

function GuidanceList({
  title,
  items,
}: {
  title: string;
  items: GuidanceItem[];
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
              <GuidanceActionButton item={item} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StageGuidancePanel({ stage }: Props) {
  const { jobRunning } = useApp();
  const guidance = stage.guidance;
  if (!guidance) {
    return (
      <div className="stage-guidance panel-inset">
        <StagePrimaryAction stage={stage} />
        <p className="hint">Run this stage to produce outputs. Progress appears in the activity panel.</p>
      </div>
    );
  }

  const allItems = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  const hasTodo = allItems.some((i) => i.status === "todo");

  return (
    <section className="stage-guidance panel-inset" aria-label="How to proceed">
      {!jobRunning ? <StagePrimaryAction stage={stage} /> : null}

      <h3 className="stage-outputs-title">
        How to proceed
        {hasTodo ? (
          <span className="stage-guidance-badge muted">Details below</span>
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

      <GuidanceList title="Before you start" items={guidance.prerequisites || []} />
      <GuidanceList title="Step checklist" items={guidance.actions || []} />

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
