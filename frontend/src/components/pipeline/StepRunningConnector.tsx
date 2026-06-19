interface Props {
  label: string;
  stepIndex?: number | null;
  stepTotal?: number | null;
}

export function StepRunningConnector({ label, stepIndex, stepTotal }: Props) {
  const progress =
    stepIndex != null && stepTotal
      ? `Step ${stepIndex} of ${stepTotal} — `
      : "";
  return (
    <li className="pipeline-step-connector" aria-live="polite">
      <span className="spinner-inline pipeline-step-connector-spinner" aria-hidden />
      <span className="pipeline-step-connector-label">
        {progress}
        {label}
      </span>
    </li>
  );
}
