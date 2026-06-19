import type { ReactNode } from "react";
import { StepDoneBanner } from "./StepDoneBanner";

interface Props {
  complete: boolean;
  title?: string;
  children: ReactNode;
  className?: string;
}

/** Gray overlay when a gate/checkpoint substep is complete. */
export function GatePanelShell({ complete, title, children, className = "" }: Props) {
  if (!complete) return <div className={className}>{children}</div>;
  return (
    <div className={`gate-panel gate-panel--done${className ? ` ${className}` : ""}`}>
      <StepDoneBanner variant="substep" title={title ?? "Gate complete"} />
      <div className="gate-panel-done-shell">{children}</div>
    </div>
  );
}
