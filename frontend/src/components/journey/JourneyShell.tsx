import type { ReactNode } from "react";
import { useApp } from "../../context/AppContext";
import { DeliverableCard } from "../workspace/DeliverableCard";
import { AudioQualityDrawer } from "../workspace/AudioQualityDrawer";

interface JourneyShellProps {
  children: ReactNode;
}

export function JourneyShell({ children }: JourneyShellProps) {
  const { run, config } = useApp();
  const enabled = config?.journey_ui?.enabled !== false;

  if (!run || !enabled) {
    return <>{children}</>;
  }

  return (
    <div className="journey-shell">
      <AudioQualityDrawer />
      {children}
      <DeliverableCard />
    </div>
  );
}
