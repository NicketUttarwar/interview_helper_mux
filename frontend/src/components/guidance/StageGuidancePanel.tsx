import type { GuidanceItem, StageInfo } from "../../types";
import { ActionMarker } from "./ActionMarker";
import { GuidanceActionButton } from "./GuidanceActionButton";
import { useApp } from "../../context/AppContext";

interface Props {
  stage: StageInfo;
  hideActions?: boolean;
}

function GuidanceList({
  title,
  items,
  stageId,
  hideActionButtons,
}: {
  title: string;
  items: GuidanceItem[];
  stageId: string;
  hideActionButtons?: boolean;
}) {
  const actionItems = hideActionButtons
    ? items.filter((i) => i.kind !== "action" && i.kind !== "checkpoint")
    : items;

  if (!actionItems.length) return null;

  return (
    <div className="stage-guidance-section">
      <h3 className="stage-guidance-heading">{title}</h3>
      <ul className="stage-guidance-list">
        {actionItems.map((item) => (
          <li
            key={item.id}
            className={`stage-guidance-item status-${item.status}`}
          >
            <ActionMarker status={item.status} />
            <span className="stage-guidance-label">{item.label}</span>
            {!hideActionButtons &&
            (item.kind === "navigate" ||
              item.kind === "checkpoint" ||
              item.kind === "action") ? (
              <span className="stage-guidance-item-actions">
                <GuidanceActionButton item={item} stageId={stageId} />
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StageGuidancePanel({ stage, hideActions = false }: Props) {
  const { run } = useApp();
  const guidance = stage.guidance;

  if (!guidance) {
    return (
      <details className="stage-guidance panel-inset">
        <summary className="stage-guidance-summary">About this step</summary>
        <p className="hint">Run this stage to produce outputs. Progress appears in the activity panel.</p>
      </details>
    );
  }

  const allItems = [...(guidance.prerequisites || []), ...(guidance.actions || [])];
  const hasTodo = allItems.some((i) => i.status === "todo");

  return (
    <details className="stage-guidance panel-inset">
      <summary className="stage-guidance-summary" aria-label="How to proceed">
        How to proceed
        {hasTodo ? (
          <span className="stage-guidance-badge muted"> checklist</span>
        ) : null}
      </summary>
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
        stageId={stage.id}
        hideActionButtons={hideActions}
      />
      <GuidanceList
        title="Step checklist"
        items={guidance.actions || []}
        stageId={stage.id}
        hideActionButtons={hideActions}
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
      {!run ? null : (
        <p className="hint sm">Use the sidebar checklist and review panel for required actions.</p>
      )}
    </details>
  );
}
