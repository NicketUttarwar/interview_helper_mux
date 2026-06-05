interface InfoTooltipProps {
  text: string;
  label?: string;
}

/** Compact info icon — detail appears on hover/focus. */
export function InfoTooltip({ text, label = "More info" }: InfoTooltipProps) {
  return (
    <span className="info-tooltip-wrap">
      <button
        type="button"
        className="info-tooltip-trigger"
        aria-label={label}
        title={text}
      >
        ⓘ
      </button>
      <span className="info-tooltip-popup" role="tooltip">
        {text}
      </span>
    </span>
  );
}
