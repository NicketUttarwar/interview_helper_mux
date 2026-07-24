import type { ReactNode } from "react";
import { StepDoneBanner } from "./StepDoneBanner";

interface Props {
  complete: boolean;
  title?: string;
  children: ReactNode;
  className?: string;
}

/** Visual "done" chrome when a gate/checkpoint substep is complete.
 * Content stays interactive so operators can still play/pause stage audio. */
export function GatePanelShell({ complete, title, children, className = "" }: Props) {
  if (!complete) return <div className={className}>{children}</div>;
  return (
    <div className={`gate-panel gate-panel--done${className ? ` ${className}` : ""}`}>
      <div className="gate-panel-done-shell">
        <StepDoneBanner variant="substep" title={title ?? "Gate complete"} />
        {children}
      </div>
    </div>
  );
}
