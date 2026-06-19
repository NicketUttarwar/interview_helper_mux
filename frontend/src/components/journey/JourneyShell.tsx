import type { ReactNode } from "react";
import { useApp } from "../../context/AppContext";
import { DeliverableCard } from "../workspace/DeliverableCard";
import { AudioQualityDrawer } from "../workspace/AudioQualityDrawer";
import { isPhaseFullyComplete } from "../../utils/phaseSubsteps";
import { StepDoneBanner } from "../pipeline/StepDoneBanner";

interface JourneyShellProps {
  children: ReactNode;
}

export function JourneyShell({ children }: JourneyShellProps) {
  const { run, config } = useApp();
  const enabled = config?.journey_ui?.enabled !== false;

  if (!run || !enabled) {
    return <>{children}</>;
  }

  const phase = run.journey?.phase ?? "prepare";
  const phaseComplete = isPhaseFullyComplete(run, phase);

  return (
    <div className={`journey-shell${phaseComplete ? " journey-phase-complete" : ""}`}>
      {phaseComplete ? (
        <StepDoneBanner
          variant="substep"
          title={`${phase.charAt(0).toUpperCase()}${phase.slice(1)} phase complete`}
        />
      ) : null}
      <AudioQualityDrawer />
      {children}
      <DeliverableCard />
    </div>
  );
}
