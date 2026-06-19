import { useApp } from "../../context/AppContext";
import { resolvePendingAction } from "../../utils/pendingAction";
import { pendingActionToSubstep } from "../../utils/stageSubsteps";

interface Props {
  compact?: boolean;
  stageId?: string;
}

export function PendingActionBanner({ compact, stageId }: Props) {
  const { run, apiGrants, activateSubstep, setActiveTab, setPipelineSubTab } = useApp();

  const pending = resolvePendingAction(run, apiGrants);
  if (!pending) return null;
  if (stageId && pending.stageId !== stageId) return null;

  const onPrimary = () => {
    setActiveTab("pipeline");
    setPipelineSubTab(pending.subTab ?? "stage");
    activateSubstep(pendingActionToSubstep(pending), { openModal: false });
  };

  const handoffMessage =
    pending.kind === "handoff" && pending.handoffPaths?.length
      ? `Skim: ${pending.handoffPaths
          .slice(0, 2)
          .map((p) => p.split("/").pop())
          .join(", ")}${pending.handoffPaths.length > 2 ? "…" : ""}`
      : pending.message;

  return (
    <div
      className={`pending-action-banner kind-${pending.kind}${compact ? " compact" : ""} attention-required`}
      role="alert"
      data-testid="pending-action-banner"
    >
      <div className="pending-action-icon" aria-hidden>
        {pending.kind === "write_approval" ? "📋" : pending.kind === "handoff" ? "✓" : "!"}
      </div>
      <div className="pending-action-copy">
        <p className="pending-action-title">
          {pending.stageTitle} — {pending.title}
        </p>
        <p className="pending-action-message">{handoffMessage}</p>
        {!compact ? (
          <p className="hint sm pending-action-hint">
            Use the <strong>Steps</strong> sidebar in Pipeline to review and continue.
          </p>
        ) : null}
      </div>
      <div className="pending-action-buttons">
        <button
          type="button"
          className="btn primary sm"
          data-testid="pending-action-primary"
          onClick={onPrimary}
        >
          Go to step in Pipeline
        </button>
      </div>
    </div>
  );
}
