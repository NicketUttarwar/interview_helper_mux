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
  const { run, config } = useApp();
  const { phase, phaseProgress } = useJourney(run);
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
      <AudioQualityDrawer />
      {children}
      <DeliverableCard />
    </div>
  );
}
