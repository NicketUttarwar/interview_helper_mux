import { useState } from "react";

interface InfoTooltipProps {
  text: string;
  label?: string;
}

/** Compact info icon — detail on hover/focus; tap toggles on touch devices. */
export function InfoTooltip({ text, label = "More info" }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);

  return (
    <span className={`info-tooltip-wrap${open ? " info-tooltip-open" : ""}`}>
      <button
        type="button"
        className="info-tooltip-trigger"
        aria-label={label}
        aria-expanded={open}
        title={text}
        onClick={() => setOpen((v) => !v)}
      >
        ⓘ
      </button>
      <span className="info-tooltip-popup" role="tooltip">
        {text}
      </span>
    </span>
  );
}
