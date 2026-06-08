import type { GuidanceItemStatus } from "../../types";

interface Props {
  status: GuidanceItemStatus;
  className?: string;
}

export function ActionMarker({ status, className = "" }: Props) {
  return (
    <span
      className={`action-marker status-${status}${className ? ` ${className}` : ""}`}
      aria-hidden
    >
      {status === "done" ? "✓" : status === "todo" ? "●" : "○"}
    </span>
  );
}
