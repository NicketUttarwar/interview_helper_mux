interface Props {
  label: string;
}

export function StepRunningConnector({ label }: Props) {
  return (
    <li className="pipeline-step-connector" aria-live="polite">
      <span className="spinner-inline pipeline-step-connector-spinner" aria-hidden />
      <span className="pipeline-step-connector-label">{label}</span>
    </li>
  );
}
