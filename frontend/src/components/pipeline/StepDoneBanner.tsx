interface Props {
  variant?: "step" | "phase" | "substep";
  title?: string;
}

const DEFAULT_TITLES: Record<NonNullable<Props["variant"]>, string> = {
  step: "This step is complete",
  phase: "Phase complete",
  substep: "Done",
};

export function StepDoneBanner({ variant = "step", title }: Props) {
  const text = title ?? DEFAULT_TITLES[variant];
  return (
    <div className={`step-done-banner step-done-banner--${variant}`} role="status">
      <span className="step-done-banner-text">{text}</span>
    </div>
  );
}
