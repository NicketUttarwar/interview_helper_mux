import type { ReactNode } from "react";
import { useApp } from "../../context/AppContext";
import { useJourney } from "../../hooks/useJourney";
import { DeliverableCard } from "../workspace/DeliverableCard";
import { AudioQualityDrawer } from "../workspace/AudioQualityDrawer";

const PHASE_LABELS: Record<string, string> = {
  prepare: "Prepare",
  understand: "Understand",
  complete: "Complete",
  create: "Create",
  polish: "Polish",
  ship: "Ship",
};

interface JourneyShellProps {
  children: ReactNode;
}

export function JourneyShell({ children }: JourneyShellProps) {
  const { run, config, executeJob, openActionModal, jobRunning } = useApp();
  const { phase, nextAction, blocking, phaseProgress, runExecuteHint, isBlocked } =
    useJourney(run);
  const enabled = config?.journey_ui?.enabled !== false;

  if (!run || !enabled) {
    return <>{children}</>;
  }

  return (
    <div className="journey-shell">
      <div className="journey-phase-bar">
        {Object.entries(PHASE_LABELS).map(([key, label]) => {
          const prog = phaseProgress[key];
          const active = key === phase;
          const done = prog && prog.total > 0 && prog.done === prog.total;
          return (
            <span
              key={key}
              className={`journey-phase-chip${active ? " active" : ""}${done ? " done" : ""}`}
            >
              {label}
              {prog && prog.total > 0 ? ` ${prog.done}/${prog.total}` : ""}
            </span>
          );
        })}
      </div>
      <div className="journey-guidance-row">
        {blocking?.blocked && blocking.message ? (
          <div className="journey-blocking-banner" role="status">
            <span>{blocking.message}</span>
            <button type="button" className="btn primary sm" data-testid="open-checkpoint" onClick={openActionModal}>
              Open checkpoint
            </button>
          </div>
        ) : nextAction ? (
          <p className="journey-next-action">
            <strong>Next:</strong> {nextAction}
          </p>
        ) : null}
        {runExecuteHint && !isBlocked ? (
          <button
            type="button"
            className="btn primary sm journey-run-cta"
            data-testid="journey-run-cta"
            disabled={jobRunning}
            onClick={() => void executeJob(runExecuteHint.body)}
          >
            {runExecuteHint.label}
          </button>
        ) : null}
      </div>
      <AudioQualityDrawer />
      {children}
      <DeliverableCard />
    </div>
  );
}
